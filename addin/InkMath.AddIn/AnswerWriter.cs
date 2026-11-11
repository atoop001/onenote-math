using System.Globalization;
using System.Net;
using System.Xml.Linq;

namespace InkMath.AddIn
{
    /// <summary>
    /// Builds the UpdatePageContent XML that adds the answer under the selection: one new Outline and nothing else,
    /// so the user's ink and text are never moved or changed (spec §3).
    /// </summary>
    public static class AnswerWriter
    {
        static readonly XNamespace One = SelectionReader.One;
        public const double Gap = 14;

        // Readable on a shared screen (spec §6.7)
        const string Step = "font-size:14pt;color:#1A1A1A";
        const string AnswerStyle = "font-size:16pt;font-weight:bold;color:#1A1A1A";
        const string Plain = "font-size:14pt;color:#1A1A1A";
        const string SourceStyle = "font-size:11pt;color:#555555";

        public static string BuildXml(string pageId, PageRect below, SolverResponse r)
        {
            var oes = new XElement(One + "OEChildren");
            void Line(string text, string style) =>
                oes.Add(new XElement(One + "OE", new XElement(One + "T",
                    new XCData($"<span style='{style}'>{WebUtility.HtmlEncode(text)}</span>"))));

            foreach (var s in r.Steps) Line(s, Step);
            var answer = r.Answer?.Text ?? "";
            Line(answer, AnswerStyle);
            var dec = r.Answer?.Decimal;
            if (!string.IsNullOrEmpty(dec) && !answer.Contains("≈")) Line("≈ " + dec, Plain);
            foreach (var n in r.Notes) Line(n, Plain);
            Line(r.Source, SourceStyle);

            var page = new XElement(One + "Page",
                new XAttribute(XNamespace.Xmlns + "one", One.NamespaceName),
                new XAttribute("ID", pageId),
                new XElement(One + "Outline",
                    new XElement(One + "Position",
                        new XAttribute("x", Fmt(below.X)), new XAttribute("y", Fmt(below.Bottom + Gap)), new XAttribute("z", "0")),
                    oes));
            return page.ToString(SaveOptions.DisableFormatting);
        }

        static string Fmt(double v) => v.ToString("0.###", CultureInfo.InvariantCulture);
    }
}
