using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Web.Script.Serialization;

namespace InkMath.AddIn
{
    /// <summary>One request to the M2 solver (solver/inkmath_solver/schema.py: Request).</summary>
    public class SolverRequest
    {
        public string Id { get; set; }
        public string Latex { get; set; }
        public string Operation { get; set; }
        public string Variable { get; set; }
        public string Point { get; set; }
        public bool ShowSteps { get; set; } = true;
    }

    public class SolverAnswer
    {
        public string Latex { get; set; }
        public string Text { get; set; }
        public string Decimal { get; set; }
    }

    /// <summary>One response line from the solver (schema.py: Response). Lists are never null.</summary>
    public class SolverResponse
    {
        public string Id { get; set; } = "";
        public string Status { get; set; } = "";
        public string Operation { get; set; }
        public string Variable { get; set; }
        public List<string> Choices { get; set; } = new List<string>();
        public List<string> Steps { get; set; } = new List<string>();
        public SolverAnswer Answer { get; set; }
        public List<string> Notes { get; set; } = new List<string>();
        public bool Verified { get; set; }
        public string Source { get; set; } = "";
        public string Message { get; set; } = "";
        public int Ms { get; set; }
    }

    /// <summary>The JSON-lines protocol of `python -m inkmath_solver`.</summary>
    public static class Protocol
    {
        static JavaScriptSerializer Json() => new JavaScriptSerializer { MaxJsonLength = int.MaxValue };

        public static string ToJson(SolverRequest r)
        {
            var d = new Dictionary<string, object> { ["id"] = r.Id, ["latex"] = r.Latex };
            if (r.Operation != null) d["operation"] = r.Operation;
            if (r.Variable != null) d["variable"] = r.Variable;
            if (r.Point != null) d["point"] = r.Point;
            d["show_steps"] = r.ShowSteps;
            return Json().Serialize(d);
        }

        public static string Control(string id, string control) =>
            Json().Serialize(new Dictionary<string, object> { ["id"] = id, ["control"] = control });

        public static bool IsReady(string line)
        {
            var d = TryObject(line);
            return d != null && d.TryGetValue("ready", out var v) && v is bool b && b;
        }

        /// <summary>Parses one response line. Throws FormatException on anything that isn't a JSON object.</summary>
        public static SolverResponse Parse(string line)
        {
            var d = TryObject(line) ?? throw new FormatException("Not a JSON object: " + line);
            var r = new SolverResponse
            {
                Id = Str(d, "id") ?? "",
                Status = Str(d, "status") ?? "",
                Operation = Str(d, "operation"),
                Variable = Str(d, "variable"),
                Choices = List(d, "choices"),
                Steps = List(d, "steps"),
                Notes = List(d, "notes"),
                Verified = d.TryGetValue("verified", out var v) && v is bool b && b,
                Source = Str(d, "source") ?? "",
                Message = Str(d, "message") ?? "",
                Ms = d.TryGetValue("ms", out var ms) && ms != null ? Convert.ToInt32(ms) : 0,
            };
            if (d.TryGetValue("answer", out var a) && a is IDictionary<string, object> ad)
                r.Answer = new SolverAnswer { Latex = Str(ad, "latex"), Text = Str(ad, "text"), Decimal = Str(ad, "decimal") };
            return r;
        }

        static IDictionary<string, object> TryObject(string line)
        {
            try { return Json().DeserializeObject(line) as IDictionary<string, object>; }
            catch (ArgumentException) { return null; }
            catch (InvalidOperationException) { return null; }
        }

        static string Str(IDictionary<string, object> d, string k) =>
            d.TryGetValue(k, out var v) && v != null ? Convert.ToString(v) : null;

        static List<string> List(IDictionary<string, object> d, string k) =>
            d.TryGetValue(k, out var v) && v is IEnumerable e && !(v is string)
                ? e.Cast<object>().Select(Convert.ToString).ToList()
                : new List<string>();
    }

    /// <summary>What each solver operation is called on screen (also M5's action menu).</summary>
    public static class OperationLabels
    {
        static readonly Dictionary<string, string> Map = new Dictionary<string, string>
        {
            ["simplify"] = "Simplify", ["factor"] = "Factor", ["expand"] = "Expand", ["solve"] = "Solve",
            ["solve_system"] = "Solve system", ["evaluate"] = "Evaluate", ["evaluate_at"] = "Evaluate at a point",
            ["derivative"] = "Derivative", ["implicit_derivative"] = "Implicit derivative", ["integrate"] = "Integrate",
            ["limit"] = "Limit", ["series"] = "Series", ["identity"] = "Check identity", ["ode"] = "Solve ODE",
        };

        public static string Label(string op) => op != null && Map.TryGetValue(op, out var l) ? l : op;
    }
}
