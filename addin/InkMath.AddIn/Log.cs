using System;
using System.IO;

namespace InkMath.AddIn
{
    /// <summary>Append-only log at %LOCALAPPDATA%\InkMath\inkmath.log. Never throws.</summary>
    public static class Log
    {
        static readonly object Gate = new object();
        public static string Dir => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "InkMath");
        public static string FilePath => Path.Combine(Dir, "inkmath.log");
        const int MaxLine = 500;

        public static void Info(string message) => Write("INFO", message);

        public static void Error(string message, Exception e) => Write("ERROR", e == null ? message : message + ": " + e);

        static void Write(string level, string message)
        {
            try
            {
                if (message != null && message.Length > MaxLine && level == "INFO") message = message.Substring(0, MaxLine) + "…";
                lock (Gate)
                {
                    Directory.CreateDirectory(Dir);
                    File.AppendAllText(FilePath, $"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff} {level} {message}{Environment.NewLine}");
                }
            }
            catch
            {
                // logging must never break the add-in
            }
        }
    }
}
