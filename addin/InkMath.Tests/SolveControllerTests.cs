using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Web.Script.Serialization;
using InkMath.AddIn;
using Xunit;
using static InkMath.Tests.TestFiles;

namespace InkMath.Tests
{
    class FakePage : IOneNotePage
    {
        public string Xml;
        public Exception ReadThrows, UpdateThrows;
        public readonly List<string> Updates = new List<string>();
        public string ReadCurrentPageSelection() => ReadThrows != null ? throw ReadThrows : Xml;
        public void Update(string xml) { if (UpdateThrows != null) throw UpdateThrows; Updates.Add(xml); }
    }

    class FakeSolver : ISolver
    {
        public SolverResponse Reply;
        public SolverResponse CheckIn;
        public Action<FakeSolver> DuringCheckIn;
        public readonly List<SolverRequest> Requests = new List<SolverRequest>();
        public readonly List<string> Continued = new List<string>(), Stopped = new List<string>();
        public bool Start() => true;
        public SolverResponse Solve(SolverRequest req, Action<SolverResponse> onCheckIn)
        {
            Requests.Add(req);
            if (CheckIn != null) { onCheckIn(CheckIn); DuringCheckIn?.Invoke(this); }
            Reply.Id = req.Id;
            return Reply;
        }
        public void Continue(string id) => Continued.Add(id);
        public void Stop(string id) => Stopped.Add(id);
        public void Dispose() { }
    }

    class FakeStore : ISelectionStore
    {
        public readonly List<InkSelection> Saved = new List<InkSelection>();
        public void SaveLast(InkSelection s) => Saved.Add(s);
    }

    public class SolveControllerTests
    {
        readonly FakePage page = new FakePage { Xml = Fixture("selection_typed.xml") };
        readonly FakeSolver solver = new FakeSolver { Reply = OkReply() };
        readonly FakeStore store = new FakeStore();
        int changes;
        SolveController C() => new SolveController(page, solver, store, () => changes++);

        static SolverResponse OkReply() => new SolverResponse
        {
            Status = "ok", Steps = new List<string> { "Add 7 to both sides" },
            Answer = new SolverAnswer { Text = "x = 6" }, Verified = true, Source = "Solved offline · verified",
        };

        [Fact]
        public void Typed_problem_is_solved_and_written()
        {
            var c = C();
            c.Solve();
            Assert.Equal("3x-7=11", solver.Requests.Single().Latex);
            Assert.Equal("r1", solver.Requests.Single().Id);
            Assert.Single(page.Updates);
            Assert.Contains("x = 6", page.Updates[0]);
            Assert.Contains("ID=\"{PAGE-1}\"", page.Updates[0]);
            Assert.Equal("Solved offline · verified", c.Status);
            Assert.False(c.Busy);
            Assert.True(changes >= 2);
        }

        [Fact]
        public void Request_ids_count_up()
        {
            var c = C();
            c.Solve();
            c.Solve();
            Assert.Equal(new[] { "r1", "r2" }, solver.Requests.Select(r => r.Id));
        }

        [Fact]
        public void Empty_selection_writes_nothing()
        {
            page.Xml = Fixture("selection_caret.xml");
            var c = C();
            c.Solve();
            Assert.Equal("Lasso a problem first.", c.Status);
            Assert.Empty(page.Updates);
            Assert.Empty(solver.Requests);
        }

        [Fact]
        public void Ink_is_saved_not_solved()
        {
            page.Xml = Fixture("selection_ink.xml");
            var c = C();
            c.Solve();
            Assert.Single(store.Saved);
            Assert.Equal(2, store.Saved[0].Ink.Count);
            Assert.Empty(solver.Requests);
            Assert.Empty(page.Updates);
            Assert.Equal("Ink saved. Handwriting reading isn't installed yet. Lasso typed text to test.", c.Status);
        }

        [Fact]
        public void Needs_operation_lists_labels()
        {
            solver.Reply = new SolverResponse { Status = "needs_operation", Choices = new List<string> { "factor", "evaluate_at" }, Message = "What should I do with this?" };
            var c = C();
            c.Solve();
            Assert.Equal("What should I do with this? Factor · Evaluate at a point", c.Status);
            Assert.Empty(page.Updates);
        }

        [Fact]
        public void Non_ok_writes_nothing()
        {
            solver.Reply = new SolverResponse { Status = "cannot_solve", Message = "Couldn't determine whether this series converges" };
            var c = C();
            c.Solve();
            Assert.Equal("Couldn't determine whether this series converges", c.Status);
            Assert.Empty(page.Updates);
        }

        [Fact]
        public void Unverified_source_is_shown()
        {
            solver.Reply = OkReply();
            solver.Reply.Verified = false;
            solver.Reply.Source = "Solved offline · ⚠ unverified";
            var c = C();
            c.Solve();
            Assert.Equal("Solved offline · ⚠ unverified", c.Status);
            Assert.Single(page.Updates);
        }

        [Fact]
        public void Checkin_sets_awaiting_and_keep_going_continues()
        {
            solver.CheckIn = new SolverResponse { Status = "still_working", Message = "This one's taking a while. Keep going or stop?" };
            var c = C();
            bool awaiting = false, busy = false;
            string status = null;
            solver.DuringCheckIn = s => { awaiting = c.AwaitingCheckIn; busy = c.Busy; status = c.Status; c.KeepGoing(); };
            c.Solve();
            Assert.True(awaiting);
            Assert.True(busy);
            Assert.Equal("This one's taking a while. Keep going or stop?", status);
            Assert.Equal(new[] { "r1" }, solver.Continued);
            Assert.False(c.AwaitingCheckIn);
        }

        [Fact]
        public void Stop_stops_the_current_request()
        {
            solver.CheckIn = new SolverResponse { Status = "still_working", Message = "…" };
            solver.Reply = new SolverResponse { Status = "stopped", Message = "Stopped." };
            var c = C();
            solver.DuringCheckIn = s => c.Stop();
            c.Solve();
            Assert.Equal(new[] { "r1" }, solver.Stopped);
            Assert.Equal("Stopped.", c.Status);
            Assert.False(c.AwaitingCheckIn);
        }

        [Fact]
        public void Stop_when_idle_does_nothing()
        {
            var c = C();
            c.Stop();
            c.KeepGoing();
            Assert.Empty(solver.Stopped);
            Assert.Empty(solver.Continued);
        }

        [Fact]
        public void Show_steps_off_is_sent()
        {
            var c = C();
            c.ShowSteps = false;
            c.Solve();
            Assert.False(solver.Requests.Single().ShowSteps);
        }

        [Fact]
        public void Write_failure_has_its_own_message()
        {
            page.UpdateThrows = new InvalidOperationException("boom");
            var c = C();
            c.Solve();
            Assert.Equal("Couldn't write the answer onto the page.", c.Status);
            Assert.False(c.Busy);
        }

        [Fact]
        public void Read_failure_is_caught()
        {
            page.ReadThrows = new InvalidOperationException("boom");
            var c = C();
            c.Solve();
            Assert.Equal("Something went wrong. Details are in the log.", c.Status);
            Assert.False(c.Busy);
        }

        [Fact]
        public void Selection_store_writes_json()
        {
            var dir = Path.Combine(Path.GetTempPath(), "inkmath-test-" + Guid.NewGuid().ToString("N"));
            try
            {
                new SelectionStore(dir).SaveLast(SelectionReader.Read(Fixture("selection_ink.xml")));
                var d = (Dictionary<string, object>)new JavaScriptSerializer().DeserializeObject(File.ReadAllText(Path.Combine(dir, "last.json")));
                Assert.Equal("{PAGE-2}", d["pageId"]);
                Assert.Equal(2, ((object[])d["ink"]).Length);
            }
            finally { if (Directory.Exists(dir)) Directory.Delete(dir, true); }
        }

        [Fact]
        public void Settings_load_and_missing()
        {
            var dir = Path.Combine(Path.GetTempPath(), "inkmath-test-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(dir);
            try
            {
                Assert.Null(AddInSettings.Load(dir));
                File.WriteAllText(Path.Combine(dir, "inkmath.settings.json"), "{\"pythonExe\":\"C:\\\\py\\\\python.exe\",\"solverDir\":\"D:\\\\s\"}");
                var s = AddInSettings.Load(dir);
                Assert.Equal(@"C:\py\python.exe", s.PythonExe);
                Assert.Equal(@"D:\s", s.SolverDir);
            }
            finally { Directory.Delete(dir, true); }
        }
    }
}
