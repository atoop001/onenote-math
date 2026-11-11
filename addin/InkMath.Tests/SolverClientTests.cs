using System;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using InkMath.AddIn;
using Xunit;
using static InkMath.Tests.TestFiles;

namespace InkMath.Tests
{
    public class SolverClientTests
    {
        const string SlowLatex = @"\int e^{x^2}\sin(x^3)\cos(\sqrt{x})dx";
        const string Crash = "Something went wrong solving this";

        static SolverSettings Real() => new SolverSettings { PythonExe = VenvPython, SolverDir = SolverDir, CheckinSeconds = 1 };

        static SolverSettings Stub(string mode) => new SolverSettings
        {
            PythonExe = VenvPython, SolverDir = SolverDir, DeadAfterSeconds = 3,
            ExtraArgs = $"\"{Path.Combine(FixtureDir, "stub_solver.py")}\" {mode}",
        };

        static SolverRequest Slow() => new SolverRequest { Id = "slow", Latex = SlowLatex, Operation = "integrate" };

        [Fact]
        public void Real_solver_roundtrip_keeps_unicode()
        {
            using (var s = new SolverClient(Real()))
            {
                Assert.True(s.Start());
                var r = s.Solve(new SolverRequest { Id = "a", Latex = "x^2=2" }, _ => { });
                Assert.Equal("ok", r.Status);
                Assert.Equal("x = −√2, x = √2", r.Answer.Text);
                Assert.Equal("Solved offline · verified", r.Source);
            }
        }

        [Fact]
        public void Checkin_then_stop()
        {
            using (var s = new SolverClient(Real()))
            {
                Assert.True(s.Start());
                var checkins = 0;
                var r = s.Solve(Slow(), c => { checkins++; Assert.Equal("This one's taking a while. Keep going or stop?", c.Message); s.Stop("slow"); });
                Assert.Equal(1, checkins);
                Assert.Equal("stopped", r.Status);
                Assert.Equal("ok", s.Solve(new SolverRequest { Id = "b", Latex = "x+1=2" }, _ => { }).Status);
            }
        }

        [Fact]
        public void Continue_keeps_it_going()
        {
            using (var s = new SolverClient(Real()))
            {
                Assert.True(s.Start());
                var checkins = 0;
                var r = s.Solve(Slow(), c => { if (++checkins == 1) s.Continue("slow"); else s.Stop("slow"); });
                Assert.Equal(2, checkins);
                Assert.Equal("stopped", r.Status);
            }
        }

        [Fact]
        public void Stop_before_checkin_from_another_thread()
        {
            var settings = Real();
            settings.CheckinSeconds = 20;
            using (var s = new SolverClient(settings))
            {
                Assert.True(s.Start());
                var sw = Stopwatch.StartNew();
                Task.Run(async () => { await Task.Delay(300); s.Stop("slow"); });
                var r = s.Solve(Slow(), _ => { });
                Assert.Equal("stopped", r.Status);
                Assert.True(sw.Elapsed < TimeSpan.FromSeconds(3), sw.Elapsed.ToString());
            }
        }

        [Fact]
        public void Survives_chatty_stderr()
        {
            using (var s = new SolverClient(Stub("stderr")))
            {
                var sw = Stopwatch.StartNew();
                var r = s.Solve(new SolverRequest { Id = "a", Latex = "x" }, _ => { });
                Assert.Equal("ok", r.Status);
                Assert.Equal("x = 6", r.Answer.Text);
                Assert.True(sw.Elapsed < TimeSpan.FromSeconds(10), sw.Elapsed.ToString());
            }
        }

        [Fact]
        public void Silent_process_is_declared_dead()
        {
            using (var s = new SolverClient(Stub("silent")))
            {
                Assert.True(s.Start());
                var sw = Stopwatch.StartNew();
                var r = s.Solve(new SolverRequest { Id = "a", Latex = "x" }, _ => { });
                Assert.Equal("error", r.Status);
                Assert.Equal(Crash, r.Message);
                Assert.InRange(sw.Elapsed.TotalSeconds, 2.9, 6);
            }
        }

        [Fact]
        public void Crashing_process_gives_error_each_time_without_hanging()
        {
            using (var s = new SolverClient(Stub("crash")))
            {
                var sw = Stopwatch.StartNew();
                Assert.Equal(Crash, s.Solve(new SolverRequest { Id = "a", Latex = "x" }, _ => { }).Message);
                Assert.Equal(Crash, s.Solve(new SolverRequest { Id = "b", Latex = "x" }, _ => { }).Message);
                Assert.True(sw.Elapsed < TimeSpan.FromSeconds(10), sw.Elapsed.ToString());
            }
        }

        [Fact]
        public void Killed_process_gives_error_and_restarts()
        {
            using (var s = new SolverClient(Real()))
            {
                Assert.True(s.Start());
                var pid = s.ProcessId.Value;
                Task.Run(async () => { await Task.Delay(500); Process.GetProcessById(pid).Kill(); });
                var r = s.Solve(Slow(), _ => { });
                Assert.Equal("error", r.Status);
                Assert.Equal(Crash, r.Message);
                var next = s.Solve(new SolverRequest { Id = "b", Latex = "x+1=2" }, _ => { });
                Assert.Equal("ok", next.Status);
                Assert.NotEqual(pid, s.ProcessId);
            }
        }

        [Fact]
        public void Missing_python_fails_fast()
        {
            using (var s = new SolverClient(new SolverSettings { PythonExe = @"C:\nope\python.exe", SolverDir = SolverDir }))
            {
                var sw = Stopwatch.StartNew();
                Assert.False(s.Start());
                var r = s.Solve(new SolverRequest { Id = "a", Latex = "x" }, _ => { });
                Assert.Equal("error", r.Status);
                Assert.Equal("The solver isn't running. Check the setup.", r.Message);
                Assert.True(sw.Elapsed < TimeSpan.FromSeconds(2), sw.Elapsed.ToString());
            }
        }

        [Fact]
        public void Dispose_ends_the_process()
        {
            Process p;
            using (var s = new SolverClient(Real()))
            {
                Assert.True(s.Start());
                p = Process.GetProcessById(s.ProcessId.Value);
            }
            Assert.True(p.WaitForExit(5000));
        }
    }
}
