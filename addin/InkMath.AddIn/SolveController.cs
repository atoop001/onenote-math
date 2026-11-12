using System;
using System.Diagnostics;
using System.Linq;
using System.Threading;

namespace InkMath.AddIn
{
    /// <summary>OneNote page access the controller needs (implemented by Com/OneNotePage).</summary>
    public interface IOneNotePage
    {
        /// <summary>Current page XML with piBinaryDataSelection.</summary>
        string ReadCurrentPageSelection();
        void Update(string xml);
    }

    /// <summary>What the ribbon shell reads and calls.</summary>
    public interface ISolveController
    {
        bool ShowSteps { get; set; }
        string Status { get; }
        bool Busy { get; }
        bool AwaitingCheckIn { get; }
        void Solve();
        void KeepGoing();
        void Stop();
    }

    public static class StatusText
    {
        public const string NothingSelected = "Lasso a problem first.";
        public const string InkSaved = "Ink saved. Handwriting reading isn't installed yet. Lasso typed text to test.";
        public const string Solving = "Solving…";
        public const string WriteFailed = "Couldn't write the answer onto the page.";
        public const string Unexpected = "Something went wrong. Details are in the log.";
        public const string NeedsOperation = "What should I do with this? ";
    }

    /// <summary>The Solve flow: selection → solver → page. Solve() runs on the worker thread; the rest is thread-safe.</summary>
    public class SolveController : ISolveController
    {
        readonly IOneNotePage page;
        readonly ISolver solver;
        readonly ISelectionStore store;
        readonly Action changed;
        int counter;
        volatile string status = "";
        volatile bool busy, awaiting, showSteps = true;
        volatile string currentId;

        public SolveController(IOneNotePage page, ISolver solver, ISelectionStore store, Action changed)
        {
            this.page = page;
            this.solver = solver;
            this.store = store;
            this.changed = changed ?? (() => { });
        }

        public bool ShowSteps { get => showSteps; set => showSteps = value; }
        public string Status => status;
        public bool Busy => busy;
        public bool AwaitingCheckIn => awaiting;

        public void Solve()
        {
            var sw = Stopwatch.StartNew();
            busy = true;
            Set(StatusText.Solving);
            long read = 0, solve = 0;
            try
            {
                var sel = SelectionReader.Read(page.ReadCurrentPageSelection());
                read = sw.ElapsedMilliseconds;
                if (sel.IsEmpty) { Set(StatusText.NothingSelected); return; }
                if (sel.Ink.Count > 0)
                {
                    store.SaveLast(sel);
                    Log.Info($"ink saved: {sel.Ink.Count} items, read {read} ms");
                    Set(StatusText.InkSaved);
                    return;
                }

                var req = new SolverRequest { Id = "r" + Interlocked.Increment(ref counter), Latex = sel.TypedText, ShowSteps = showSteps };
                currentId = req.Id;
                var r = solver.Solve(req, OnCheckIn);
                currentId = null;
                awaiting = false;
                solve = sw.ElapsedMilliseconds - read;
                if (r.Status != "ok") { Set(MessageFor(r)); return; }

                try { page.Update(AnswerWriter.BuildXml(sel.PageId, sel.Bounds, r)); }
                catch (Exception e)
                {
                    Log.Error("writing the answer", e);
                    Set(StatusText.WriteFailed);
                    return;
                }
                Set(r.Source);
                Log.Info($"solved {req.Id}: read {read} ms, solve {solve} ms (server {r.Ms} ms), write {sw.ElapsedMilliseconds - read - solve} ms");
            }
            catch (Exception e)
            {
                Log.Error("solve", e);
                Set(StatusText.Unexpected);
            }
            finally
            {
                currentId = null;
                awaiting = false;
                busy = false;
                Notify();
            }
        }

        void OnCheckIn(SolverResponse r)
        {
            awaiting = true;
            Set(r.Message);
        }

        public void KeepGoing()
        {
            var id = currentId;
            if (id == null) return;
            solver.Continue(id);
            awaiting = false;
            Set(StatusText.Solving);
        }

        public void Stop()
        {
            var id = currentId;
            if (id == null) return;
            solver.Stop(id);
        }

        static string MessageFor(SolverResponse r) =>
            r.Status == "needs_operation"
                ? StatusText.NeedsOperation + string.Join(" · ", r.Choices.Select(OperationLabels.Label))
                : r.Message;

        void Set(string s)
        {
            status = s ?? "";
            Notify();
        }

        void Notify()
        {
            try { changed(); }
            catch (Exception e) { Log.Error("status change callback", e); }
        }
    }
}
