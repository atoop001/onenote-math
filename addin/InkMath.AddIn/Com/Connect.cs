using System;
using System.Collections.Concurrent;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;

namespace InkMath.AddIn
{
    /// <summary>
    /// The COM add-in OneNote loads (in a dllhost surrogate). Ribbon callbacks only read state or queue work: all
    /// OneNote I/O and solver I/O run on one background STA worker thread (spec §3: never hang OneNote).
    /// Every public entry point catches everything, because an exception makes OneNote disable the add-in.
    /// </summary>
    [ComVisible(true)]
    [Guid("7E3C1B52-4A9D-4F0E-9C61-2B8D5A4F3E17")]
    [ProgId("InkMath.Connect")]
    [ClassInterface(ClassInterfaceType.AutoDispatch)]
    public class Connect : IDTExtensibility2, IRibbonExtensibility
    {
        const string Offline = "Offline";
        ISolveController controller;
        SolverClient solver;
        BlockingCollection<Action> queue;
        Thread worker;
        SynchronizationContext ui;
        Control uiControl;
        object ribbon;
        bool pendingShowSteps = true;
        int solvePending;

        public Connect() { }

        internal Connect(ISolveController controller, bool startWorker = false)
        {
            this.controller = controller;
            if (startWorker) StartWorker();
        }

        // ---------- IDTExtensibility2 ----------

        public void OnConnection(object Application, ext_ConnectMode ConnectMode, object AddInInst, ref Array custom)
        {
            try
            {
                Log.Info($"OnConnection ({ConnectMode}), pid {System.Diagnostics.Process.GetCurrentProcess().Id}, {(Environment.Is64BitProcess ? 64 : 32)}-bit");
                var apartment = Thread.CurrentThread.GetApartmentState();
                Log.Info("ribbon thread apartment: " + apartment);
                if (apartment == ApartmentState.STA)
                {
                    // An STA thread pumps messages, so ribbon refreshes are posted back to it.
                    uiControl = new Control();
                    var unused = uiControl.Handle;              // the marshaling window lives on this (ribbon) thread
                    ui = new WindowsFormsSynchronizationContext();
                }
                // In the MTA (dllhost may host a "Both" object there) nothing pumps messages: the ribbon proxy
                // is usable from any MTA thread, so Changed() calls Invalidate from the thread pool instead.

                var settings = AddInSettings.Load(DllDir());
                if (settings == null) Log.Info("no " + AddInSettings.FileName + " beside the add-in; the solver can't start");
                solver = new SolverClient(new SolverSettings { PythonExe = settings?.PythonExe, SolverDir = settings?.SolverDir });

                StartWorker();

                var c = new SolveController(new LazyPage(), solver, new SelectionStore(), Changed) { ShowSteps = pendingShowSteps };
                controller = c;
            }
            catch (Exception e)
            {
                Log.Error("OnConnection", e);
            }
        }

        public void OnDisconnection(ext_DisconnectMode RemoveMode, ref Array custom)
        {
            try { Log.Info("OnDisconnection " + RemoveMode); Shutdown(); }
            catch (Exception e) { Log.Error("OnDisconnection", e); }
        }

        public void OnAddInsUpdate(ref Array custom) { }

        public void OnStartupComplete(ref Array custom)
        {
            try
            {
                var s = solver;
                if (s != null) Enqueue(() => Log.Info(s.Start() ? "solver started" : "solver failed to start"));
            }
            catch (Exception e) { Log.Error("OnStartupComplete", e); }
        }

        public void OnBeginShutdown(ref Array custom)
        {
            try { Shutdown(); }
            catch (Exception e) { Log.Error("OnBeginShutdown", e); }
        }

        // ---------- IRibbonExtensibility ----------

        public string GetCustomUI(string RibbonID)
        {
            try
            {
                Log.Info("GetCustomUI " + RibbonID);
                using (var s = typeof(Connect).Assembly.GetManifestResourceStream("InkMath.AddIn.Ribbon.xml"))
                using (var r = new StreamReader(s))
                    return r.ReadToEnd();
            }
            catch (Exception e)
            {
                Log.Error("GetCustomUI", e);
                return "";
            }
        }

        // ---------- ribbon callbacks (names match Ribbon.xml) ----------

        public void OnRibbonLoad(object ribbonUI)
        {
            try { ribbon = ribbonUI; }
            catch (Exception e) { Log.Error("OnRibbonLoad", e); }
        }

        public void OnSolve(object control)
        {
            try
            {
                var c = controller;
                if (c == null || c.Busy) return;
                // One solve at a time, counted from the tap: taps while one is queued or running are ignored.
                if (Interlocked.CompareExchange(ref solvePending, 1, 0) != 0) return;
                Changed();
                Enqueue(() =>
                {
                    try { c.Solve(); }
                    finally { Interlocked.Exchange(ref solvePending, 0); Changed(); }
                });
            }
            catch (Exception e) { Log.Error("OnSolve", e); }
        }

        public void OnKeepGoing(object control)
        {
            try { controller?.KeepGoing(); }
            catch (Exception e) { Log.Error("OnKeepGoing", e); }
        }

        public void OnStop(object control)
        {
            try { controller?.Stop(); }
            catch (Exception e) { Log.Error("OnStop", e); }
        }

        public void OnToggleSteps(object control, bool pressed)
        {
            try
            {
                pendingShowSteps = pressed;
                if (controller != null) controller.ShowSteps = pressed;
            }
            catch (Exception e) { Log.Error("OnToggleSteps", e); }
        }

        public bool GetPressed(object control)
        {
            try { return controller?.ShowSteps ?? pendingShowSteps; }
            catch (Exception e) { Log.Error("GetPressed", e); return false; }
        }

        public bool GetEnabled(object control)
        {
            try
            {
                var c = controller;
                switch (IdOf(control))
                {
                    case "solveButton": return Volatile.Read(ref solvePending) == 0 && (c == null || !c.Busy);
                    case "keepGoingButton": return c != null && c.AwaitingCheckIn;
                    case "stopButton": return c != null && c.Busy;
                    default: return false;
                }
            }
            catch (Exception e) { Log.Error("GetEnabled", e); return false; }
        }

        public string GetLabel(object control)
        {
            try
            {
                switch (IdOf(control))
                {
                    case "badgeLabel": return Offline;
                    case "statusLabel":
                        var s = controller?.Status;
                        return string.IsNullOrEmpty(s) ? " " : s;     // an empty label collapses the group
                    default: return " ";
                }
            }
            catch (Exception e) { Log.Error("GetLabel", e); return " "; }
        }

        // ---------- plumbing ----------

        static string IdOf(object control)
        {
            if (control == null) return null;
            dynamic d = control;
            return (string)d.Id;
        }

        internal void Enqueue(Action a)
        {
            var q = queue;
            if (q == null || q.IsAddingCompleted)
            {
                try { a(); } catch (Exception e) { Log.Error("work item", e); }   // no worker (tests / not connected)
                return;
            }
            q.Add(a);
        }

        void StartWorker()
        {
            queue = new BlockingCollection<Action>();
            var q = queue;
            worker = new Thread(() => WorkerLoop(q)) { IsBackground = true, Name = "InkMath worker" };
            worker.SetApartmentState(ApartmentState.STA);
            worker.Start();
        }

        static void WorkerLoop(BlockingCollection<Action> q)
        {
            foreach (var a in q.GetConsumingEnumerable())
            {
                try { a(); }
                catch (Exception e) { Log.Error("work item", e); }
            }
        }

        internal void Changed()
        {
            var ctx = ui;
            var r = ribbon;
            if (r == null) return;
            SendOrPostCallback invalidate = _ =>
            {
                try { ((dynamic)r).Invalidate(); }
                catch (Exception e) { Log.Error("ribbon Invalidate", e); }
            };
            if (ctx != null) ctx.Post(invalidate, null);
            else ThreadPool.QueueUserWorkItem(o => invalidate(o));
        }

        void Shutdown()
        {
            var c = controller;
            try { c?.Stop(); } catch (Exception e) { Log.Error("stop on shutdown", e); }
            queue?.CompleteAdding();
            solver?.Dispose();
            solver = null;
            try { uiControl?.Dispose(); } catch { /* ignore */ }
            uiControl = null;
        }

        static string DllDir() => Path.GetDirectoryName(new Uri(typeof(Connect).Assembly.CodeBase).LocalPath);

        /// <summary>Creates the real OneNotePage on first use, which happens on the worker thread.</summary>
        sealed class LazyPage : IOneNotePage
        {
            OneNotePage page;
            OneNotePage P => page ?? (page = new OneNotePage());
            public string ReadCurrentPageSelection() => P.ReadCurrentPageSelection();
            public void Update(string xml) => P.Update(xml);
        }
    }
}
