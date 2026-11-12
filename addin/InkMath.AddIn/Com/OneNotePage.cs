using System;
using System.Linq;
using System.Reflection;
using System.Xml.Linq;

namespace InkMath.AddIn
{
    /// <summary>
    /// OneNote access through its own late-bound OneNote.Application, created on (and used only from) the worker thread.
    /// Calls go through plain IDispatch (Type.InvokeMember), never C# dynamic, and only to methods of the Application
    /// object: dynamic asks for type info and OneNote's window objects need the type library, and both fail on
    /// machines where Office left the OneNote type library half-registered (seen on the dev PC).
    /// </summary>
    public sealed class OneNotePage : IOneNotePage
    {
        const int PiBinaryDataSelection = 3;
        internal const int ScopeNotebooks = 2;
        const int ScopePages = 4;
        const int Xs2013 = 2;   // XMLSchema.xs2013: what SelectionReader expects; newer builds default to a 2026 schema
        object app;

        object App => app ?? (app = Activator.CreateInstance(Type.GetTypeFromProgID("OneNote.Application", true)));

        /// <summary>The ID of the page marked isCurrentlyViewed in a GetHierarchy result, or null.</summary>
        internal static string CurrentPageId(string hierarchyXml) =>
            (string)XDocument.Parse(hierarchyXml).Descendants(SelectionReader.One + "Page")
                .FirstOrDefault(p => (string)p.Attribute("isCurrentlyViewed") == "true")?.Attribute("ID");

        internal string Hierarchy(int scope) => (string)Call("GetHierarchy", 2, "", scope, "", Xs2013);

        public string ReadCurrentPageSelection()
        {
            var pageId = CurrentPageId(Hierarchy(ScopePages));
            if (string.IsNullOrEmpty(pageId)) throw new InvalidOperationException("No OneNote page is open");
            return (string)Call("GetPageContent", 1, pageId, "", PiBinaryDataSelection, Xs2013);
        }

        public void Update(string xml) => Call("UpdatePageContent", -1, xml, DateTime.MinValue, Xs2013, false);

        /// <summary>Invokes an Application method; returns the out argument at <paramref name="outIndex"/> (or null).</summary>
        object Call(string method, int outIndex, params object[] args)
        {
            var mods = new ParameterModifier(args.Length);
            if (outIndex >= 0) mods[outIndex] = true;
            try
            {
                App.GetType().InvokeMember(method, BindingFlags.InvokeMethod, null, App, args, new[] { mods }, null, null);
            }
            catch (TargetInvocationException e) when (e.InnerException != null)
            {
                throw e.InnerException;
            }
            return outIndex >= 0 ? args[outIndex] : null;
        }
    }
}
