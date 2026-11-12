using System;
using System.Diagnostics;
using System.IO;
using System.Threading;
using InkMath.AddIn;
using Xunit;
using static InkMath.Tests.TestFiles;

namespace InkMath.Tests
{
    public class ReaderClientTests : IDisposable
    {
        readonly string marker = Path.Combine(Path.GetTempPath(), "inkmath-reader-" + Guid.NewGuid().ToString("N"));
        static readonly byte[][] Ink = { new byte[] { 1, 2, 3 }, new byte[] { 4, 5 } };

        ReaderSettings Stub(string mode) => new ReaderSettings
        {
            PythonExe = VenvPython, ReaderDir = RepoRoot, ReadTimeoutSeconds = 2,
            ExtraArgs = $"\"{Path.Combine(FixtureDir, "stub_reader.py")}\" {mode} \"{marker}\"",
        };

        static void WaitReady(ReaderClient r)
        {
            var deadline = DateTime.UtcNow.AddSeconds(15);
            while (!r.Ready && DateTime.UtcNow < deadline) Thread.Sleep(50);
            Assert.True(r.Ready, "reader never became ready");
        }

        [Fact]
        public void Reads_ok_reply_with_symbols()
        {
            using (var r = new ReaderClient(Stub("ok")))
            {
                r.StartInBackground();
                WaitReady(r);
                var res = r.Read("k1", Ink);
                Assert.Equal("ok", res.Status);
                Assert.Equal("3x-7=11", res.Latex);
                Assert.Equal(7, res.Symbols.Count);
                Assert.True(res.Symbols[3].Low);
                Assert.Equal(new[] { "1", "\\tau" }, res.Symbols[3].Alternatives);
                Assert.Equal(3, res.Symbols[3].Start);
                Assert.Equal(1400, res.TotalMs);
                Assert.Equal("texteller", res.Model);
                Assert.Equal(@"C:\snip\last.png", res.Snippet);
            }
        }

        [Fact]
        public void Not_ready_returns_starting_immediately()
        {
            using (var r = new ReaderClient(Stub("slowready")))
            {
                r.StartInBackground();
                var sw = Stopwatch.StartNew();
                var res = r.Read("k1", Ink);
                Assert.True(sw.ElapsedMilliseconds < 200, sw.ElapsedMilliseconds + " ms");
                Assert.Equal("starting", res.Status);
                Assert.Equal(ReaderClient.Starting, res.Message);
            }
        }

        [Fact]
        public void Silent_reader_times_out_and_restarts()
        {
            using (var r = new ReaderClient(Stub("silent")))
            {
                r.StartInBackground();
                WaitReady(r);
                var sw = Stopwatch.StartNew();
                var res = r.Read("k1", Ink);
                Assert.Equal("error", res.Status);
                Assert.Equal(ReaderClient.Failed, res.Message);
                Assert.InRange(sw.Elapsed.TotalSeconds, 1.9, 6);
                WaitReady(r);
                Assert.Equal("ok", r.Read("k2", Ink).Status);
            }
        }

        [Fact]
        public void Crashed_reader_errors_then_recovers()
        {
            using (var r = new ReaderClient(Stub("crash")))
            {
                r.StartInBackground();
                WaitReady(r);
                Assert.Equal(ReaderClient.Failed, r.Read("k1", Ink).Message);
                WaitReady(r);
                Assert.Equal("ok", r.Read("k2", Ink).Status);
            }
        }

        [Fact]
        public void Missing_python_reports_error_without_waiting()
        {
            using (var r = new ReaderClient(new ReaderSettings { PythonExe = @"C:\nope\python.exe", ReaderDir = RepoRoot }))
            {
                r.StartInBackground();
                var deadline = DateTime.UtcNow.AddSeconds(5);
                ReaderResult res;
                do { res = r.Read("k1", Ink); Thread.Sleep(50); } while (res.Status == "starting" && DateTime.UtcNow < deadline);
                Assert.Equal("error", res.Status);
                Assert.Equal(ReaderClient.Failed, res.Message);
            }
        }

        [Fact]
        public void Dispose_never_blocks()
        {
            var r = new ReaderClient(Stub("slowready"));
            r.StartInBackground();
            Thread.Sleep(500);
            var sw = Stopwatch.StartNew();
            r.Dispose();
            Assert.True(sw.ElapsedMilliseconds < 500, sw.ElapsedMilliseconds + " ms");
        }

        public void Dispose()
        {
            try { File.Delete(marker); } catch { /* best effort */ }
        }
    }
}
