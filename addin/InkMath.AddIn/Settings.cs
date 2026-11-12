using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Web.Script.Serialization;

namespace InkMath.AddIn
{
    /// <summary>inkmath.settings.json beside the add-in DLL, written by install/register.ps1.</summary>
    public class AddInSettings
    {
        public const string FileName = "inkmath.settings.json";
        public string PythonExe { get; set; }
        public string SolverDir { get; set; }
        public string ReaderPythonExe { get; set; }
        public string ReaderDir { get; set; }
        public string ModelsDir { get; set; }

        /// <summary>Null when the file is missing or unreadable.</summary>
        public static AddInSettings Load(string dllDir)
        {
            var path = Path.Combine(dllDir, FileName);
            if (!File.Exists(path)) return null;
            try
            {
                var d = (IDictionary<string, object>)new JavaScriptSerializer().DeserializeObject(File.ReadAllText(path));
                return new AddInSettings
                {
                    PythonExe = d.TryGetValue("pythonExe", out var p) ? p as string : null,
                    SolverDir = d.TryGetValue("solverDir", out var s) ? s as string : null,
                    ReaderPythonExe = d.TryGetValue("readerPythonExe", out var rp) ? rp as string : null,
                    ReaderDir = d.TryGetValue("readerDir", out var rd) ? rd as string : null,
                    ModelsDir = d.TryGetValue("modelsDir", out var md) ? md as string : null,
                };
            }
            catch (Exception e)
            {
                Log.Error("reading " + path, e);
                return null;
            }
        }
    }

    public interface ISelectionStore
    {
        void SaveLast(InkSelection s);
    }

    /// <summary>Keeps the last lassoed ink as sample input for M4. Local only (spec §6.6).</summary>
    public class SelectionStore : ISelectionStore
    {
        readonly string dir;

        public SelectionStore(string dir = null)
        {
            this.dir = dir ?? Path.Combine(Log.Dir, "selections");
        }

        public void SaveLast(InkSelection s)
        {
            Directory.CreateDirectory(dir);
            object Rect(PageRect r) => new Dictionary<string, object> { ["x"] = r.X, ["y"] = r.Y, ["width"] = r.Width, ["height"] = r.Height };
            var d = new Dictionary<string, object>
            {
                ["pageId"] = s.PageId,
                ["bounds"] = Rect(s.Bounds),
                ["ink"] = s.Ink.Select(i => new Dictionary<string, object> { ["isf"] = Convert.ToBase64String(i.Isf), ["bounds"] = Rect(i.Bounds) }).ToArray(),
            };
            File.WriteAllText(Path.Combine(dir, "last.json"), new JavaScriptSerializer { MaxJsonLength = int.MaxValue }.Serialize(d));
        }
    }
}
