using System;
using System.Diagnostics;
using System.IO;
using Microsoft.Win32;
using Xunit;
using static InkMath.Tests.TestFiles;

namespace InkMath.Tests
{
    public class RegistrationTests : IDisposable
    {
        const string Clsid = "{7E3C1B52-4A9D-4F0E-9C61-2B8D5A4F3E17}";
        readonly string prefix = @"Software\InkMathTest-" + Guid.NewGuid().ToString("N");
        readonly string dir = Path.Combine(Path.GetTempPath(), "inkmath-reg-" + Guid.NewGuid().ToString("N"));
        readonly string dll;

        public RegistrationTests()
        {
            Directory.CreateDirectory(dir);
            dll = Path.Combine(dir, "InkMath.AddIn.dll");
            File.Copy(typeof(InkMath.AddIn.Connect).Assembly.Location, dll);
        }

        static readonly RegistryView[] Views = { RegistryView.Registry32, RegistryView.Registry64 };

        static int Run(string script, string args)
        {
            var psi = new ProcessStartInfo("powershell.exe",
                $"-NoProfile -NonInteractive -ExecutionPolicy Bypass -File \"{Path.Combine(RepoRoot, "install", script)}\" {args}")
            { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
            using (var p = Process.Start(psi))
            {
                var err = p.StandardError.ReadToEnd();
                p.StandardOutput.ReadToEnd();
                Assert.True(p.WaitForExit(60000), "script timed out");
                Assert.True(p.ExitCode == 0, script + " failed: " + err);
                return p.ExitCode;
            }
        }

        string RegisterArgs => $"-DllPath \"{dll}\" -PythonExe \"C:\\py\\python.exe\" -SolverDir \"D:\\s\" -KeyPrefix \"{prefix}\"";

        static object Value(RegistryView view, string key, string name)
        {
            using (var root = RegistryKey.OpenBaseKey(RegistryHive.CurrentUser, view))
            using (var k = root.OpenSubKey(key))
                return k?.GetValue(name);
        }

        [Fact]
        public void Register_writes_both_views_and_settings()
        {
            Run("register.ps1", RegisterArgs);
            foreach (var v in Views)
            {
                var cls = $@"{prefix}\Classes\CLSID\{Clsid}";
                Assert.Equal("InkMath.Connect", Value(v, cls, ""));
                Assert.Equal(Clsid, Value(v, cls, "AppID"));
                Assert.Equal("mscoree.dll", Value(v, cls + @"\InprocServer32", ""));
                Assert.Equal("InkMath.AddIn.Connect", Value(v, cls + @"\InprocServer32", "Class"));
                Assert.Equal("Both", Value(v, cls + @"\InprocServer32", "ThreadingModel"));
                Assert.Equal("InkMath.AddIn, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null", Value(v, cls + @"\InprocServer32", "Assembly"));
                Assert.Equal("v4.0.30319", Value(v, cls + @"\InprocServer32", "RuntimeVersion"));
                Assert.EndsWith("InkMath.AddIn.dll", (string)Value(v, cls + @"\InprocServer32", "CodeBase"));
                Assert.StartsWith("file:///", (string)Value(v, cls + @"\InprocServer32", "CodeBase"));
                Assert.Equal("InkMath.Connect", Value(v, cls + @"\ProgId", ""));
                Assert.Equal("", Value(v, $@"{prefix}\Classes\AppID\{Clsid}", "DllSurrogate"));
                Assert.Equal(Clsid, Value(v, $@"{prefix}\Classes\InkMath.Connect\CLSID", ""));
            }
            var addin = $@"{prefix}\Microsoft\Office\OneNote\AddIns\InkMath.Connect";
            Assert.Equal(3, Value(RegistryView.Default, addin, "LoadBehavior"));
            Assert.Equal("Ink Math", Value(RegistryView.Default, addin, "FriendlyName"));
            Assert.Equal("Solve handwritten math", Value(RegistryView.Default, addin, "Description"));
            var settings = InkMath.AddIn.AddInSettings.Load(dir);
            Assert.Equal(@"C:\py\python.exe", settings.PythonExe);
            Assert.Equal(@"D:\s", settings.SolverDir);
        }

        [Fact]
        public void Register_writes_reader_settings()
        {
            Run("register.ps1", RegisterArgs + " -ReaderPythonExe \"C:\\rp\\python.exe\" -ReaderDir \"D:\\r\" -ModelsDir \"D:\\m\"");
            var settings = InkMath.AddIn.AddInSettings.Load(dir);
            Assert.Equal(@"C:\rp\python.exe", settings.ReaderPythonExe);
            Assert.Equal(@"D:\r", settings.ReaderDir);
            Assert.Equal(@"D:\m", settings.ModelsDir);
            Assert.Equal(@"C:\py\python.exe", settings.PythonExe);
        }

        [Fact]
        public void Register_without_python_writes_no_settings()
        {
            Run("register.ps1", $"-DllPath \"{dll}\" -KeyPrefix \"{prefix}\"");
            Assert.False(File.Exists(Path.Combine(dir, "inkmath.settings.json")));
            Assert.Equal("InkMath.AddIn.Connect", Value(RegistryView.Registry64, $@"{prefix}\Classes\CLSID\{Clsid}\InprocServer32", "Class"));
        }

        [Fact]
        public void Unregister_removes_everything()
        {
            Run("register.ps1", RegisterArgs);
            Run("unregister.ps1", $"-KeyPrefix \"{prefix}\"");
            foreach (var v in Views)
            using (var root = RegistryKey.OpenBaseKey(RegistryHive.CurrentUser, v))
            {
                Assert.Null(root.OpenSubKey($@"{prefix}\Classes\CLSID\{Clsid}"));
                Assert.Null(root.OpenSubKey($@"{prefix}\Classes\AppID\{Clsid}"));
                Assert.Null(root.OpenSubKey($@"{prefix}\Classes\InkMath.Connect"));
                Assert.Null(root.OpenSubKey($@"{prefix}\Microsoft\Office\OneNote\AddIns\InkMath.Connect"));
            }
        }

        const string TypeLib = "{0EA692EE-BB50-4E3C-AEF0-356D91732725}";
        const string OneNoteExe = @"C:\Office\ONENOTE.EXE\3";

        // A fake machine registration like the dev PC's: version 1.0 holds only a PIA name, 1.1 has the file.
        void FakeTypeLibSource(bool broken)
        {
            using (var root = RegistryKey.OpenBaseKey(RegistryHive.CurrentUser, RegistryView.Default))
            {
                if (broken)
                    using (var k = root.CreateSubKey($@"{prefix}\Src\TypeLib\{TypeLib}\1.0"))
                        k.SetValue("PrimaryInteropAssemblyName", "Microsoft.Office.Interop.OneNote");
                using (var k = root.CreateSubKey($@"{prefix}\Src\TypeLib\{TypeLib}\1.1\0\win32"))
                    k.SetValue("", OneNoteExe);
            }
        }

        string RepairArgs => $"-DllPath \"{dll}\" -KeyPrefix \"{prefix}\" -TypeLibSourceHive CurrentUser -TypeLibSourceKey \"{prefix}\\Src\\TypeLib\"";

        [Fact]
        public void Register_repairs_a_half_registered_onenote_type_library()
        {
            FakeTypeLibSource(broken: true);
            Run("register.ps1", RepairArgs);
            Assert.Equal(OneNoteExe, Value(RegistryView.Default, $@"{prefix}\Classes\TypeLib\{TypeLib}\1.0\0\win32", ""));
            Assert.Null(Value(RegistryView.Default, $@"{prefix}\Classes\TypeLib\{TypeLib}\1.1\0\win32", ""));

            Run("unregister.ps1", $"-KeyPrefix \"{prefix}\"");
            using (var root = RegistryKey.OpenBaseKey(RegistryHive.CurrentUser, RegistryView.Default))
                Assert.Null(root.OpenSubKey($@"{prefix}\Classes\TypeLib\{TypeLib}\1.0"));
        }

        [Fact]
        public void Register_leaves_a_healthy_type_library_alone()
        {
            FakeTypeLibSource(broken: false);
            Run("register.ps1", RepairArgs);
            using (var root = RegistryKey.OpenBaseKey(RegistryHive.CurrentUser, RegistryView.Default))
                Assert.Null(root.OpenSubKey($@"{prefix}\Classes\TypeLib\{TypeLib}"));
        }

        [Fact]
        public void Unregister_keeps_type_library_entries_it_did_not_write()
        {
            using (var root = RegistryKey.OpenBaseKey(RegistryHive.CurrentUser, RegistryView.Default))
            using (var k = root.CreateSubKey($@"{prefix}\Classes\TypeLib\{TypeLib}\1.0\0\win32"))
                k.SetValue("", OneNoteExe);
            Run("unregister.ps1", $"-KeyPrefix \"{prefix}\"");
            Assert.Equal(OneNoteExe, Value(RegistryView.Default, $@"{prefix}\Classes\TypeLib\{TypeLib}\1.0\0\win32", ""));
        }

        public void Dispose()
        {
            foreach (var v in Views)
                using (var root = RegistryKey.OpenBaseKey(RegistryHive.CurrentUser, v))
                    root.DeleteSubKeyTree(prefix, false);
            try { Directory.Delete(dir, true); } catch { /* best effort */ }
        }
    }
}
