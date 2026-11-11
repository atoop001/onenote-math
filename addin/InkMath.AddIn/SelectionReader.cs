using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Net;
using System.Text.RegularExpressions;
using System.Xml.Linq;

namespace InkMath.AddIn
{
    /// <summary>A rectangle in OneNote page coordinates (points).</summary>
    public struct PageRect
    {
        public PageRect(double x, double y, double width, double height) { X = x; Y = y; Width = width; Height = height; }
        public double X { get; }
        public double Y { get; }
        public double Width { get; }
        public double Height { get; }
        public double Bottom => Y + Height;
        public double Right => X + Width;

        public PageRect Union(PageRect o)
        {
            double x = Math.Min(X, o.X), y = Math.Min(Y, o.Y);
            return new PageRect(x, y, Math.Max(Right, o.Right) - x, Math.Max(Bottom, o.Bottom) - y);
        }

        public override string ToString() => $"({X}, {Y}, {Width}×{Height})";
    }

    /// <summary>One piece of selected ink: the raw ISF bytes and where it sits on the page.</summary>
    public class InkItem
    {
        public byte[] Isf { get; set; }
        public PageRect Bounds { get; set; }
    }

    public class InkSelection
    {
        public string PageId { get; set; }
        public List<InkItem> Ink { get; set; } = new List<InkItem>();
        public string TypedText { get; set; } = "";
        public PageRect Bounds { get; set; }
        public bool IsEmpty => Ink.Count == 0 && string.IsNullOrWhiteSpace(TypedText);
    }

    /// <summary>Reads the lassoed selection out of GetPageContent(..., piBinaryDataSelection) XML.</summary>
    public static class SelectionReader
    {
        public static readonly XNamespace One = "http://schemas.microsoft.com/office/onenote/2013/onenote";
        static readonly Regex Tags = new Regex("<[^>]*>");

        public static InkSelection Read(string pageXml)
        {
            var page = XDocument.Parse(pageXml).Root;
            var s = new InkSelection { PageId = (string)page.Attribute("ID") };
            PageRect? bounds = null;
            void Add(PageRect r) => bounds = bounds.HasValue ? bounds.Value.Union(r) : r;

            foreach (var d in page.Elements(One + "InkDrawing").Where(IsSelected))
            {
                var r = RectOf(d);
                s.Ink.Add(new InkItem { Isf = DataOf(d), Bounds = r });
                Add(r);
            }

            var text = new List<string>();
            foreach (var outline in page.Elements(One + "Outline"))
            {
                var r = RectOf(outline);
                foreach (var w in outline.Descendants(One + "InkWord").Where(IsSelected))
                {
                    s.Ink.Add(new InkItem { Isf = DataOf(w), Bounds = r });
                    Add(r);
                }
                foreach (var t in outline.Descendants(One + "T").Where(IsSelected))
                {
                    var plain = WebUtility.HtmlDecode(Tags.Replace(t.Value, "")).Trim();
                    if (plain.Length == 0) continue;       // a bare caret
                    text.Add(plain);
                    Add(r);
                }
            }

            s.TypedText = string.Join("\n", text).Trim();
            s.Bounds = bounds ?? default;
            return s;
        }

        static bool IsSelected(XElement e)
        {
            var v = (string)e.Attribute("selected");
            return v == "all" || v == "partial";
        }

        static PageRect RectOf(XElement e)
        {
            var p = e.Element(One + "Position");
            var z = e.Element(One + "Size");
            return new PageRect(Num(p, "x"), Num(p, "y"), Num(z, "width"), Num(z, "height"));
        }

        static double Num(XElement e, string attr) =>
            e?.Attribute(attr) is XAttribute a ? double.Parse(a.Value, CultureInfo.InvariantCulture) : 0;

        static byte[] DataOf(XElement e)
        {
            var data = e.Element(One + "Data")?.Value;
            return string.IsNullOrWhiteSpace(data) ? new byte[0] : Convert.FromBase64String(data.Trim());
        }
    }
}
