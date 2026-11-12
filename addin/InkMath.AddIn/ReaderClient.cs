using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Web.Script.Serialization;

namespace InkMath.AddIn
{
    public class ReaderSettings
    {
        public string PythonExe { get; set; }
        public string ReaderDir { get; set; }
        public string ModelsDir { get; set; }
        /// <summary>A cold TexTeller load takes ~36 s on the dev PC; the Surface is slower.</summary>
        public double ReadyTimeoutSeconds { get; set; } = 120;
        public double ReadTimeoutSeconds { get; set; } = 30;
        /// <summary>Replaces "-m inkmath_reader --models ..." when set (tests run a stub).</summary>
        public string ExtraArgs { get; set; }
    }

    public class ReaderSymbol
    {
        public string Text { get; set; }
        public int Start { get; set; }
        public int End { get; set; }
        public double Confidence { get; set; }
        public bool Low { get; set; }
        public List<string> Alternatives { get; set; } = new List<string>();
    }

    public class ReaderResult
    {
        public string Status { get; set; } = "";
        public string Message { get; set; } = "";
        public string Latex { get; set; } = "";
        public List<ReaderSymbol> Symbols { get; set; } = new List<ReaderSymbol>();
        public string Snippet { get; set; }
        public string Model { get; set; }
        public int TotalMs { get; set; }
    }

    public interface IReader : IDisposable
    {
        /// <summary>The model is loaded and the process is alive.</summary>
        bool Ready { get; }
        /// <summary>Starts loading on a thread-pool thread and returns at once.</summary>
        void StartInBackground();
        /// <summary>Blocks the calling (worker) thread for one read; returns "starting" at once when not ready. Never throws.</summary>
        ReaderResult Read(string id, IList<byte[]> isf);
    }

    /// <summary>Keeps one warm `python -m inkmath_reader` process (M4 protocol, see the M4 plan).</summary>
    public sealed class ReaderClient : IReader
    {
        public const string Starting = "The handwriting reader is still starting. Try again in a moment.";
        public const string Failed = "Couldn't read this handwriting.";

        readonly ReaderSettings settings;
        readonly JsonLinesProcess process;
        readonly object readGate = new object();
        int starting;            // 1 while a background start runs
        volatile bool startFailed;

        public ReaderClient(ReaderSettings settings)
        {
            this.settings = settings;
            var args = settings.ExtraArgs ?? "-m inkmath_reader" +
                       (string.IsNullOrEmpty(settings.ModelsDir) ? "" : " --models \"" + settings.ModelsDir + "\"");
            process = new JsonLinesProcess(settings.PythonExe, args, settings.ReaderDir, null,
                                           settings.ReadyTimeoutSeconds, IsReadyLine, "reader");
        }

        public bool Ready => process.Alive;

        public void StartInBackground()
        {
            if (Interlocked.CompareExchange(ref starting, 1, 0) != 0) return;
            ThreadPool.QueueUserWorkItem(_ =>
            {
                try { startFailed = !process.Start(); }
                catch (Exception e) { startFailed = true; Log.Error("reader start", e); }
                finally { Interlocked.Exchange(ref starting, 0); }
            });
        }

        public ReaderResult Read(string id, IList<byte[]> isf)
        {
            try
            {
                if (!Ready)
                {
                    var failed = startFailed && Volatile.Read(ref starting) == 0;
                    StartInBackground();
                    return failed ? Error(id, "error", Failed) : Error(id, "starting", Starting);
                }
                lock (readGate)
                {
                    var q = process.Lines;
                    var req = new JavaScriptSerializer { MaxJsonLength = int.MaxValue }.Serialize(new Dictionary<string, object>
                    {
                        ["id"] = id, ["op"] = "read", ["ink"] = isf.Select(Convert.ToBase64String).ToArray(),
                    });
                    if (!process.Write(req)) return Crashed(id, "could not write request");
                    var timeout = TimeSpan.FromSeconds(settings.ReadTimeoutSeconds);
                    while (true)
                    {
                        var line = JsonLinesProcess.ReadLine(q, timeout, out var ended);
                        if (line == null) return Crashed(id, ended ? "reader process ended" : "no reply for " + timeout.TotalSeconds + " s");
                        ReaderResult r;
                        string rid;
                        try { r = Parse(line, out rid); }
                        catch (Exception) { Log.Info("reader sent non-JSON: " + line); continue; }
                        if (rid != id) { Log.Info("skipped reader line for other id: " + line); continue; }
                        return r;
                    }
                }
            }
            catch (Exception e)
            {
                Log.Error("reader read", e);
                return Error(id, "error", Failed);
            }
        }

        ReaderResult Crashed(string id, string why)
        {
            Log.Info("reader restart: " + why);
            process.Kill();
            startFailed = false;
            StartInBackground();
            return Error(id, "error", Failed);
        }

        static ReaderResult Error(string id, string status, string message) => new ReaderResult { Status = status, Message = message };

        static bool IsReadyLine(string line)
        {
            try { return new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(line) is var d && Str(d, "status") == "ready"; }
            catch (Exception) { return false; }
        }

        static string Str(IDictionary<string, object> d, string key) => d != null && d.TryGetValue(key, out var v) && v != null ? Convert.ToString(v, System.Globalization.CultureInfo.InvariantCulture) : null;

        static double Num(IDictionary<string, object> d, string key) =>
            d != null && d.TryGetValue(key, out var v) && v != null ? Convert.ToDouble(v, System.Globalization.CultureInfo.InvariantCulture) : 0;

        internal static ReaderResult Parse(string line, out string id)
        {
            var d = new JavaScriptSerializer { MaxJsonLength = int.MaxValue }.Deserialize<Dictionary<string, object>>(line);
            id = Str(d, "id");
            var r = new ReaderResult
            {
                Status = Str(d, "status") ?? "",
                Message = Str(d, "message") ?? "",
                Latex = Str(d, "latex") ?? "",
                Snippet = Str(d, "snippet"),
                Model = Str(d, "model"),
            };
            if (d.TryGetValue("ms", out var ms) && ms is IDictionary<string, object> msd) r.TotalMs = (int)Num(msd, "total");
            if (d.TryGetValue("symbols", out var syms) && syms is IEnumerable list)
                foreach (var o in list.OfType<IDictionary<string, object>>())
                    r.Symbols.Add(new ReaderSymbol
                    {
                        Text = Str(o, "text"),
                        Start = (int)Num(o, "start"),
                        End = (int)Num(o, "end"),
                        Confidence = Num(o, "confidence"),
                        Low = o.TryGetValue("low", out var low) && low is bool b && b,
                        Alternatives = o.TryGetValue("alternatives", out var alts) && alts is IEnumerable al
                            ? al.OfType<object>().Select(x => Convert.ToString(x)).ToList() : new List<string>(),
                    });
            return r;
        }

        public void Dispose() => process.Dispose();
    }
}
