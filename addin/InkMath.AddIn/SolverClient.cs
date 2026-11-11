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
        readonly object startGate = new object();
        readonly object solveGate = new object();
        readonly object writeGate = new object();
        Process proc;
        StreamWriter stdin;
        BlockingCollection<string> lines;
        bool ready;
        bool disposed;

        public SolverClient(SolverSettings settings) { this.settings = settings; }

        internal int? ProcessId
        {
            get { lock (startGate) { try { return proc?.Id; } catch (InvalidOperationException) { return null; } } }
        }

        public bool Start()
        {
            lock (startGate)
            {
                if (disposed) return false;
                if (ready && Alive(proc)) return true;
                KillLocked();
                try
                {
                    Launch();
                }
                catch (Exception e) when (e is Win32Exception || e is InvalidOperationException || e is IOException)
                {
                    Log.Error("solver failed to launch (" + settings.PythonExe + ")", e);
                    KillLocked();
                    return false;
                }

                var deadline = DateTime.UtcNow.AddSeconds(settings.ReadyTimeoutSeconds);
                while (true)
                {
                    var left = deadline - DateTime.UtcNow;
                    if (left <= TimeSpan.Zero || !lines.TryTake(out var line, left))
                    {
                        Log.Info("solver did not become ready");
                        KillLocked();
                        return false;
                    }
                    if (Protocol.IsReady(line)) { ready = true; Log.Info("solver ready, pid " + proc.Id); return true; }
                    Log.Info("solver (before ready): " + line);
                }
            }
        }

        void Launch()
        {
            var args = settings.ExtraArgs
                       ?? "-m inkmath_solver --checkin " + settings.CheckinSeconds.ToString(CultureInfo.InvariantCulture);
            var psi = new ProcessStartInfo(settings.PythonExe, args)
            {
                WorkingDirectory = settings.SolverDir,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardInput = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding = Encoding.UTF8,
            };
            psi.EnvironmentVariables["PYTHONUTF8"] = "1";
            var p = Process.Start(psi) ?? throw new InvalidOperationException("Process.Start returned null");
            var q = new BlockingCollection<string>();
            proc = p;
            lines = q;
            stdin = new StreamWriter(p.StandardInput.BaseStream, new UTF8Encoding(false)) { AutoFlush = true, NewLine = "\n" };

            var outReader = p.StandardOutput;
            var errReader = p.StandardError;
            new Thread(() =>
            {
                try { string l; while ((l = outReader.ReadLine()) != null) q.Add(l); }
                catch (Exception e) { Log.Error("solver stdout reader", e); }
                finally { q.CompleteAdding(); }
            }) { IsBackground = true, Name = "InkMath solver stdout" }.Start();
            new Thread(() =>
            {
                try { string l; while ((l = errReader.ReadLine()) != null) Log.Info("solver: " + l); }
                catch (Exception e) { Log.Error("solver stderr reader", e); }
            }) { IsBackground = true, Name = "InkMath solver stderr" }.Start();
        }

        public SolverResponse Solve(SolverRequest req, Action<SolverResponse> onCheckIn)
        {
            lock (solveGate)
            {
                if (!Start()) return Error(req.Id, NotRunning);
                BlockingCollection<string> q;
                lock (startGate) q = lines;
                if (!Write(Protocol.ToJson(req))) return Crashed(req.Id, "could not write request");

                var dead = TimeSpan.FromSeconds(settings.DeadAfterSeconds);
                while (true)
                {
                    if (!q.TryTake(out var line, dead))
                        return Crashed(req.Id, q.IsCompleted ? "solver process ended" : "no line for " + dead.TotalSeconds + " s");
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

        public void Continue(string id) => Write(Protocol.Control(id, "continue"));

        public void Stop(string id) => Write(Protocol.Control(id, "stop"));

        bool Write(string line)
        {
            lock (writeGate)
            {
                StreamWriter w;
                lock (startGate) w = stdin;
                if (w == null) return false;
                try { w.WriteLine(line); return true; }
                catch (Exception e) when (e is IOException || e is ObjectDisposedException)
                {
                    Log.Error("writing to solver", e);
                    return false;
                }
            }
        }

        SolverResponse Crashed(string id, string why)
        {
            Log.Info("solver restart: " + why);
            lock (startGate) KillLocked();
            ThreadPool.QueueUserWorkItem(_ => Start());     // warm again for the next solve
            return Error(id, CrashMessage);
        }

        static SolverResponse Error(string id, string message) => new SolverResponse { Id = id, Status = "error", Message = message };

        static bool Alive(Process p)
        {
            try { return p != null && !p.HasExited; }
            catch (InvalidOperationException) { return false; }
        }

        void KillLocked()
        {
            ready = false;
            var p = proc;
            proc = null;
            try { stdin?.Dispose(); } catch { /* already gone */ }
            stdin = null;
            if (p == null) return;
            try { if (!p.HasExited) p.Kill(); } catch { /* raced with exit */ }
            try { p.WaitForExit(3000); p.Dispose(); } catch { /* best effort */ }
        }

        public void Dispose()
        {
            lock (startGate)
            {
                if (disposed) return;
                disposed = true;
                ready = false;
                var p = proc;
                try { stdin?.Dispose(); } catch { /* ignore */ }     // EOF: the server exits on its own
                stdin = null;
                try { if (p != null && !p.WaitForExit(3000)) p.Kill(); } catch { /* ignore */ }
                proc = null;
            }
        }
    }
}
