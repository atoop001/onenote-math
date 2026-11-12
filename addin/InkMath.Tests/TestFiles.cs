using System;
using System.IO;

namespace InkMath.Tests
{
    static class TestFiles
    {
        public static string FixtureDir => Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "fixtures");

        public static string Fixture(string name) => File.ReadAllText(Path.Combine(FixtureDir, name));

        /// <summary>Repo root: walk up from the test assembly until a .git folder appears.</summary>
        public static string RepoRoot
        {
            get
            {
                var d = new DirectoryInfo(AppDomain.CurrentDomain.BaseDirectory);
                while (d != null && !Directory.Exists(Path.Combine(d.FullName, ".git"))) d = d.Parent;
                return d?.FullName ?? throw new InvalidOperationException("repo root not found");
            }
        }

        public static string VenvPython => Path.Combine(RepoRoot, "solver", ".venv", "Scripts", "python.exe");
        public static string SolverDir => Path.Combine(RepoRoot, "solver");
    }
}
