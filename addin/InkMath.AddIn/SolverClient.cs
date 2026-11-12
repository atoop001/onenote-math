using System;
using System.Collections.Concurrent;
using System.ComponentModel;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Text;
using System.Threading;

namespace InkMath.AddIn
{
    public class SolverSettings
    {
        public string PythonExe { get; set; }
        public string SolverDir { get; set; }
        public double CheckinSeconds { get; set; } = 20;
        public double DeadAfterSeconds { get; set; } = 25;
        public double ReadyTimeoutSeconds { get; set; } = 60;
        /// <summary>Replaces "-m inkmath_solver --checkin N" when set (tests run a stub).</summary>
        public string ExtraArgs { get; set; }
    }

    public interface ISolver : IDisposable
    {
        /// <summary>Launch and wait for {"ready": true}. False on failure. Safe to call again.</summary>
        bool Start();
        /// <summary>Blocks the calling (worker) thread until the final response. Never throws.</summary>
        SolverResponse Solve(SolverRequest req, Action<SolverResponse> onCheckIn);
        void Continue(string id);
        void Stop(string id);
    }

    /// <summary>Keeps one warm `python -m inkmath_solver` process and speaks its JSON-lines protocol.</summary>
    public sealed class SolverClient : ISolver
    {
        public const string NotRunning = "The solver isn't running. Check the setup.";
        public const string CrashMessage = "Something went wrong solving this";

        readonly SolverSettings settings;
        readonly object solveGate = new object();
        readonly JsonLinesProcess process;

        public SolverClient(SolverSettings settings)
        {
            this.settings = settings;
            var args = settings.ExtraArgs
                       ?? "-m inkmath_solver --checkin " + settings.CheckinSeconds.ToString(CultureInfo.InvariantCulture);
            process = new JsonLinesProcess(settings.PythonExe, args, settings.SolverDir, null,
                                           settings.ReadyTimeoutSeconds, Protocol.IsReady, "solver");
        }

        internal int? ProcessId => process.ProcessId;

        public bool Start() => process.Start();

        public SolverResponse Solve(SolverRequest req, Action<SolverResponse> onCheckIn)
        {
            lock (solveGate)
            {
                if (!Start()) return Error(req.Id, NotRunning);
                var q = process.Lines;
                if (!process.Write(Protocol.ToJson(req))) return Crashed(req.Id, "could not write request");

                var dead = TimeSpan.FromSeconds(settings.DeadAfterSeconds);
                while (true)
                {
                    var line = JsonLinesProcess.ReadLine(q, dead, out var ended);
                    if (line == null)
                        return Crashed(req.Id, ended ? "solver process ended" : "no line for " + dead.TotalSeconds + " s");
                    SolverResponse r;
                    try { r = Protocol.Parse(line); }
                    catch (FormatException) { Log.Info("solver sent non-JSON: " + line); continue; }
                    if (r.Id != req.Id) { Log.Info("skipped line for other id: " + line); continue; }
                    if (r.Status == "still_working")
                    {
                        try { onCheckIn?.Invoke(r); }
                        catch (Exception e) { Log.Error("check-in handler", e); }
                        continue;
                    }
                    return r;
                }
            }
        }

        public void Continue(string id) => process.Write(Protocol.Control(id, "continue"));

        public void Stop(string id) => process.Write(Protocol.Control(id, "stop"));

        SolverResponse Crashed(string id, string why)
        {
            Log.Info("solver restart: " + why);
            process.Kill();
            ThreadPool.QueueUserWorkItem(_ => Start());     // warm again for the next solve
            return Error(id, CrashMessage);
        }

        static SolverResponse Error(string id, string message) => new SolverResponse { Id = id, Status = "error", Message = message };

        /// <summary>Returns at once: closes stdin (the server exits on EOF) and kills it after 3 s if it hasn't.</summary>
        public void Dispose() => process.Dispose();
    }
}
