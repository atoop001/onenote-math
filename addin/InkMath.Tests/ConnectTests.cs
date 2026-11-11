using System;
using System.Linq;
using System.Runtime.InteropServices;
using System.Xml.Linq;
using InkMath.AddIn;
using Xunit;

namespace InkMath.Tests
{
    public class FakeControl
    {
        public FakeControl(string id) { Id = id; }
        public string Id { get; }
    }

    public class FakeRibbon
    {
        public readonly System.Threading.ManualResetEventSlim Invalidated = new System.Threading.ManualResetEventSlim();
        public void Invalidate() => Invalidated.Set();
    }

    class ThrowingController : ISolveController
    {
        static Exception E => new InvalidOperationException("boom");
        public bool ShowSteps { get => throw E; set => throw E; }
        public string Status => throw E;
        public bool Busy => throw E;
        public bool AwaitingCheckIn => throw E;
        public void Solve() => throw E;
        public void KeepGoing() => throw E;
        public void Stop() => throw E;
    }

    public class ConnectTests
    {
        static FakeControl Ctl(string id) => new FakeControl(id);

        [Fact]
        public void Ribbon_xml_is_valid_and_every_callback_exists()
        {
            var xml = new Connect().GetCustomUI("Microsoft.OneNote.Page");
            var doc = XDocument.Parse(xml);
            var callbacks = doc.Descendants().SelectMany(e => e.Attributes())
                .Where(a => a.Name.LocalName.StartsWith("on") || a.Name.LocalName.StartsWith("get"))
                .Select(a => a.Value).Distinct().ToList();
            Assert.NotEmpty(callbacks);
            foreach (var name in callbacks) Assert.NotNull(typeof(Connect).GetMethod(name));
            Assert.Equal("Math", (string)doc.Descendants().Single(e => (string)e.Attribute("id") == "inkMathTab").Attribute("label"));
            foreach (var id in new[] { "solveButton", "showStepsToggle", "keepGoingButton", "stopButton", "badgeLabel", "statusLabel" })
                Assert.Single(doc.Descendants(), e => (string)e.Attribute("id") == id);
            Assert.Equal("http://schemas.microsoft.com/office/2009/07/customui", doc.Root.Name.NamespaceName);
        }

        [Fact]
        public void Com_identity()
        {
            var t = typeof(Connect);
            Assert.Equal("7E3C1B52-4A9D-4F0E-9C61-2B8D5A4F3E17", ((GuidAttribute)t.GetCustomAttributes(typeof(GuidAttribute), false).Single()).Value.ToUpperInvariant());
            Assert.Equal("InkMath.Connect", ((ProgIdAttribute)t.GetCustomAttributes(typeof(ProgIdAttribute), false).Single()).Value);
            Assert.True(((ComVisibleAttribute)t.GetCustomAttributes(typeof(ComVisibleAttribute), false).Single()).Value);
            Assert.True(typeof(IDTExtensibility2).IsAssignableFrom(t));
            Assert.True(typeof(IRibbonExtensibility).IsAssignableFrom(t));
            Assert.Equal("B65AD801-ABAF-11D0-BB8B-00A0C90F2744", typeof(IDTExtensibility2).GUID.ToString().ToUpperInvariant());
            Assert.Equal("000C0396-0000-0000-C000-000000000046", typeof(IRibbonExtensibility).GUID.ToString().ToUpperInvariant());
        }

        [Fact]
        public void Labels_and_enabled_when_idle()
        {
            var c = new Connect();
            Assert.Equal("Offline", c.GetLabel(Ctl("badgeLabel")));
            Assert.Equal(" ", c.GetLabel(Ctl("statusLabel")));
            Assert.True(c.GetEnabled(Ctl("solveButton")));
            Assert.False(c.GetEnabled(Ctl("stopButton")));
            Assert.False(c.GetEnabled(Ctl("keepGoingButton")));
            Assert.True(c.GetPressed(Ctl("showStepsToggle")));
        }

        [Fact]
        public void Toggle_and_status_flow_through_to_controller()
        {
            var page = new FakePage { Xml = TestFiles.Fixture("selection_caret.xml") };
            var ctl = new SolveController(page, new FakeSolver(), new FakeStore(), null);
            var c = new Connect(ctl);
            c.OnToggleSteps(Ctl("showStepsToggle"), false);
            Assert.False(ctl.ShowSteps);
            Assert.False(c.GetPressed(Ctl("showStepsToggle")));
            ctl.Solve();
            Assert.Equal("Lasso a problem first.", c.GetLabel(Ctl("statusLabel")));
        }

        [Fact]
        public void Callbacks_never_throw_when_controller_throws()
        {
            var c = new Connect(new ThrowingController());
            c.OnSolve(Ctl("solveButton"));
            c.OnKeepGoing(Ctl("keepGoingButton"));
            c.OnStop(Ctl("stopButton"));
            c.OnToggleSteps(Ctl("showStepsToggle"), true);
            Assert.False(c.GetPressed(Ctl("showStepsToggle")));
            Assert.False(c.GetEnabled(Ctl("solveButton")));
            Assert.Equal(" ", c.GetLabel(Ctl("statusLabel")));
            c.OnRibbonLoad(null);
            Assert.False(c.GetEnabled(null));
            Assert.Equal(" ", c.GetLabel(null));
            Array custom = new object[0];
            c.OnBeginShutdown(ref custom);
            c.OnDisconnection(ext_DisconnectMode.ext_dm_HostShutdown, ref custom);
        }

        [Fact]
        public void Connection_lifecycle_without_onenote_does_not_throw()
        {
            var c = new Connect();
            Array custom = new object[0];
            c.OnConnection(null, ext_ConnectMode.ext_cm_Startup, null, ref custom);
            c.OnStartupComplete(ref custom);
            c.OnAddInsUpdate(ref custom);
            c.OnBeginShutdown(ref custom);
            c.OnDisconnection(ext_DisconnectMode.ext_dm_HostShutdown, ref custom);
        }

        [Fact]
        public void Ribbon_refreshes_when_connected_on_a_non_pumping_mta_thread()
        {
            var ribbon = new FakeRibbon();
            Connect c = null;
            var t = new System.Threading.Thread(() =>
            {
                c = new Connect();
                Array custom = new object[0];
                c.OnConnection(null, ext_ConnectMode.ext_cm_Startup, null, ref custom);
                c.OnRibbonLoad(ribbon);
            });
            t.SetApartmentState(System.Threading.ApartmentState.MTA);
            t.Start();
            t.Join();
            try
            {
                c.Changed();
                Assert.True(ribbon.Invalidated.Wait(3000), "ribbon.Invalidate was never called");
            }
            finally
            {
                Array custom = new object[0];
                c.OnBeginShutdown(ref custom);
            }
        }
    }
}
