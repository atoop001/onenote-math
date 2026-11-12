using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading;

namespace InkMath.AddIn
{
    /// <summary>
    /// One warm Python process speaking JSON lines: launch, wait for its ready line, write requests, read replies.
    /// Shared by SolverClient and ReaderClient. Write, Kill-from-outside and Dispose never wait on a slow Start
    /// (spec §3: never hang OneNote): they only touch volatile fields and the write gate.
    /// </summary>
    public sealed class JsonLinesProcess : IDisposable
    {
        readonly string exe, args, workDir, logName;
        readonly IDictionary<string, string> env;
        readonly double readyTimeoutSeconds;
        readonly Func<string, bool> isReady;
        readonly object startGate = new object();
        readonly object writeGate = new object();
        volatile Process proc;
        volatile StreamWriter stdin;
        volatile BlockingCollection<string> lines;
        volatile bool ready;
        volatile bool disposed;

        public JsonLinesProcess(string exe, string args, string workDir, IDictionary<string, string> env,
                                double readyTimeoutSeconds, Func<string, bool> isReady, string logName)
        {
            this.exe = exe; this.args = args; this.workDir = workDir; this.env = env;
            this.readyTimeoutSeconds = readyTimeoutSeconds; this.isReady = isReady; this.logName = logName;
        }

        /// <summary>The ready line the process printed, once it is ready.</summary>
        public string ReadyLine { get; private set; }

        public bool Alive => ready && IsRunning(proc);

        public int? ProcessId
        {
            get { lock (startGate) { try { return proc?.Id; } catch (InvalidOperationException) { return null; } } }
        }

        /// <summary>Launch (if not already running) and wait for the ready line. False on failure.</summary>
        public bool Start()
        {
            lock (startGate)
            {
                if (disposed) return false;
                if (ready && IsRunning(proc)) return true;
                KillLocked();
                try
                {
                    Launch();
                }
                catch (Exception e)
                {
                    Log.Error(logName + " failed to launch (" + exe + ")", e);
                    KillLocked();
                    return false;
                }

                var q = lines;
                var deadline = DateTime.UtcNow.AddSeconds(readyTimeoutSeconds);
                while (true)
                {
                    var left = deadline - DateTime.UtcNow;
                    if (disposed || left <= TimeSpan.Zero || !q.TryTake(out var line, left))
                    {
                        Log.Info(logName + " did not become ready");
                        KillLocked();
                        return false;
                    }
                    if (isReady(line)) { ReadyLine = line; ready = true; Log.Info(logName + " ready, pid " + proc.Id); return true; }
                    Log.Info(logName + " (before ready): " + line);
                }
            }
        }

        void Launch()
        {
            var psi = new ProcessStartInfo(exe, args)
            {
                WorkingDirectory = workDir,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardInput = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding = Encoding.UTF8,
            };
            psi.EnvironmentVariables["PYTHONUTF8"] = "1";
            if (env != null) foreach (var kv in env) psi.EnvironmentVariables[kv.Key] = kv.Value;
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
                catch (Exception e) { Log.Error(logName + " stdout reader", e); }
                finally { q.CompleteAdding(); }
            }) { IsBackground = true, Name = "InkMath " + logName + " stdout" }.Start();
            new Thread(() =>
            {
                try { string l; while ((l = errReader.ReadLine()) != null) Log.Info(logName + ": " + l); }
                catch (Exception e) { Log.Error(logName + " stderr reader", e); }
            }) { IsBackground = true, Name = "InkMath " + logName + " stderr" }.Start();
        }

        /// <summary>The current process's reply queue (capture it before writing a request).</summary>
        public BlockingCollection<string> Lines => lines;

        /// <summary>The next line from <paramref name="q"/>, or null on timeout; <paramref name="ended"/> is true when the process's output closed.</summary>
        public static string ReadLine(BlockingCollection<string> q, TimeSpan timeout, out bool ended)
        {
            ended = false;
            if (q == null) { ended = true; return null; }
            if (q.TryTake(out var line, timeout)) return line;
            ended = q.IsCompleted;
            return null;
        }

        public bool Write(string line)
        {
            lock (writeGate)
            {
                var w = stdin;
                if (w == null) return false;
                try { w.WriteLine(line); return true; }
                catch (Exception e)       // includes races with a concurrent close
                {
                    Log.Error("writing to " + logName, e);
                    return false;
                }
            }
        }

        public void Kill()
        {
            lock (startGate) KillLocked();
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

        static bool IsRunning(Process p)
        {
            try { return p != null && !p.HasExited; }
            catch (InvalidOperationException) { return false; }
        }

        /// <summary>Returns at once: closes stdin (the server exits on EOF) and kills it after 3 s if it hasn't.</summary>
        public void Dispose()
        {
            if (disposed) return;
            disposed = true;
            ready = false;
            var p = proc;
            var w = stdin;
            stdin = null;
            ThreadPool.QueueUserWorkItem(_ =>
            {
                lock (writeGate) { try { w?.Dispose(); } catch { /* already gone */ } }
                try { if (p != null && !p.WaitForExit(3000)) p.Kill(); } catch { /* raced with exit */ }
            });
        }
    }
}
