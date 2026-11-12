using System;
using System.Linq;
using InkMath.AddIn;
using Xunit;

namespace InkMath.Tests
{
    public class OneNotePageTests
    {
        [Fact]
        public void Current_page_is_the_page_marked_currently_viewed()
        {
            Assert.Equal("{PAGE-2}", OneNotePage.CurrentPageId(TestFiles.Fixture("hierarchy_pages.xml")));
        }

        [Fact]
        public void No_current_page_when_only_notebook_and_section_are_marked()
        {
            var xml = TestFiles.Fixture("hierarchy_pages.xml").Replace(" name=\"p2\" isCurrentlyViewed=\"true\"", " name=\"p2\"");
            Assert.Null(OneNotePage.CurrentPageId(xml));
        }

        // Live check against the installed OneNote: its window objects can't be late-bound on machines whose OneNote
        // type library registration is incomplete (seen on the dev PC), so the add-in must not rely on them.
        [Fact]
        public void Reads_the_notebook_tree_from_installed_onenote()
        {
            if (Type.GetTypeFromProgID("OneNote.Application") == null) return;   // OneNote not installed
            var xml = new OneNotePage().Hierarchy(OneNotePage.ScopeNotebooks);
            Assert.Contains("Notebooks", xml);
            Assert.Contains("xmlns:one=\"" + SelectionReader.One.NamespaceName + "\"", xml);   // newer builds default to a 2026 schema
        }

        // Writes an answer to a temporary page in the current section, then deletes that page permanently.
        [Fact]
        public void Writes_an_answer_to_installed_onenote()
        {
            if (Type.GetTypeFromProgID("OneNote.Application") == null) return;
            if (System.Diagnostics.Process.GetProcessesByName("ONENOTE").Length == 0) return;
            var one = Activator.CreateInstance(Type.GetTypeFromProgID("OneNote.Application"));
            var sections = (string)Invoke(one, "GetHierarchy", 2, "", 3, "", 2);
            var section = System.Xml.Linq.XDocument.Parse(sections).Descendants(SelectionReader.One + "Section")
                .FirstOrDefault(s => (string)s.Attribute("isCurrentlyViewed") == "true");
            if (section == null) return;
            var pageId = (string)Invoke(one, "CreateNewPage", 1, (string)section.Attribute("ID"), "", 0);
            try
            {
                var r = new SolverResponse { Status = "ok", Answer = new SolverAnswer { Text = "x = 6" }, Source = "Solved offline · verified" };
                new OneNotePage().Update(AnswerWriter.BuildXml(pageId, new PageRect(36, 120, 200, 30), r));
                var page = (string)Invoke(one, "GetPageContent", 1, pageId, "", 0, 2);
                Assert.Contains("x = 6", page);
            }
            finally
            {
                Invoke(one, "DeleteHierarchy", -1, pageId, DateTime.MinValue, true);
            }
        }

        static object Invoke(object o, string method, int outIndex, params object[] args)
        {
            var mods = new System.Reflection.ParameterModifier(args.Length);
            if (outIndex >= 0) mods[outIndex] = true;
            o.GetType().InvokeMember(method, System.Reflection.BindingFlags.InvokeMethod, null, o, args, new[] { mods }, null, null);
            return outIndex >= 0 ? args[outIndex] : null;
        }

        // Needs OneNote open on a page; returns early otherwise.
        [Fact]
        public void Reads_the_open_page_in_the_2013_schema()
        {
            if (Type.GetTypeFromProgID("OneNote.Application") == null) return;
            if (System.Diagnostics.Process.GetProcessesByName("ONENOTE").Length == 0) return;
            var xml = new OneNotePage().ReadCurrentPageSelection();
            Assert.Contains("xmlns:one=\"" + SelectionReader.One.NamespaceName + "\"", xml);
        }
    }
}
