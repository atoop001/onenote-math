using System;

namespace InkMath.AddIn
{
    /// <summary>
    /// OneNote access through its own late-bound OneNote.Application, created on (and used only from) the worker thread.
    /// </summary>
    public sealed class OneNotePage : IOneNotePage
    {
        const int PiBinaryDataSelection = 3;
        dynamic app;

        dynamic App => app ?? (app = Activator.CreateInstance(Type.GetTypeFromProgID("OneNote.Application", true)));

        public string ReadCurrentPageSelection()
        {
            string pageId = App.Windows.CurrentWindow?.CurrentPageId;
            if (string.IsNullOrEmpty(pageId)) throw new InvalidOperationException("No OneNote page is open");
            string xml;
            App.GetPageContent(pageId, out xml, PiBinaryDataSelection);
            return xml;
        }

        public void Update(string xml) => App.UpdatePageContent(xml);
    }
}
