using System;
using System.Diagnostics;
using System.Globalization;
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
        public const string ReaderNotSetUp = "Handwriting reading isn't set up. Check the setup.";
        /// <summary>Until M5's confirm panel: show what was read; nothing is solved (spec §6.2).</summary>
        public const int MaxLatexInStatus = 60;
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
        readonly IReader reader;
        readonly ISelectionStore store;
        readonly Action changed;
        int counter, inkCounter;
        volatile string status = "";
        volatile bool busy, awaiting, showSteps = true;
        volatile string currentId;

        /// <param name="reader">Null when handwriting reading isn't configured.</param>
        public SolveController(IOneNotePage page, ISolver solver, IReader reader, ISelectionStore store, Action changed)
        {
            this.page = page;
            this.solver = solver;
            this.reader = reader;
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
                    ReadInk(sel, sw);
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

        void ReadInk(InkSelection sel, Stopwatch sw)
        {
            if (reader == null) { Set(StatusText.ReaderNotSetUp); return; }
            var id = "k" + Interlocked.Increment(ref inkCounter);
            var r = reader.Read(id, sel.Ink.Select(i => i.Isf).ToList());
            if (r.Status != "ok") { Set(r.Message); Log.Info($"read {id}: {r.Status}"); return; }
            var low = r.Symbols.Count(s => s.Low);
            var latex = r.Latex.Length > StatusText.MaxLatexInStatus ? r.Latex.Substring(0, StatusText.MaxLatexInStatus) + "…" : r.Latex;
            var secs = (sw.ElapsedMilliseconds / 1000.0).ToString("0.0", CultureInfo.InvariantCulture);
            Set($"Read: {latex} · {secs} s" + (low > 0 ? $" · {low} to check" : ""));
            Log.Info($"read {id}: {r.Latex} · {low} low · {sw.ElapsedMilliseconds} ms (reader {r.TotalMs} ms) · {r.Model}");
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
