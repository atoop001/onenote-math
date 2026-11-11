using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Text.RegularExpressions;
using System.Xml.Linq;
using InkMath.AddIn;
using Xunit;

namespace InkMath.Tests
{
    public class AnswerWriterTests
    {
        static readonly XNamespace One = "http://schemas.microsoft.com/office/onenote/2013/onenote";

        static SolverResponse Ok(params string[] steps) => new SolverResponse
        {
            Id = "a", Status = "ok", Steps = steps.ToList(),
            Answer = new SolverAnswer { Text = "x = −√2, x = √2", Decimal = "−1.41421, 1.41421" },
            Notes = new List<string> { "x ≠ 2" }, Source = "Solved offline · verified",
        };

        static XElement Xml(string s) => XElement.Parse(s);

        static string[] Cdata(string xml) =>
            Xml(xml).Descendants(One + "OE").Select(oe => oe.Element(One + "T").Value).ToArray();

        static string[] Texts(string xml) =>
            Cdata(xml).Select(c => WebUtility.HtmlDecode(Regex.Replace(c, "<[^>]*>", ""))).ToArray();

        static readonly PageRect Box = new PageRect(36, 120, 200, 30);

        [Fact]
        public void Lines_in_order()
        {
            var lines = Texts(AnswerWriter.BuildXml("P1", Box, Ok("Quadratic formula")));
            Assert.Equal(new[] { "Quadratic formula", "x = −√2, x = √2", "≈ −1.41421, 1.41421", "x ≠ 2", "Solved offline · verified" }, lines);
        }

        [Fact]
        public void Placed_under_selection()
        {
            var pos = Xml(AnswerWriter.BuildXml("P1", new PageRect(36.5, 120, 200, 30), Ok())).Descendants(One + "Position").Single();
            Assert.Equal("36.5", (string)pos.Attribute("x"));
            Assert.Equal("164", (string)pos.Attribute("y"));
            Assert.Equal("0", (string)pos.Attribute("z"));
        }

        [Fact]
        public void Only_one_outline_and_nothing_else()
        {
            var page = Xml(AnswerWriter.BuildXml("P1", new PageRect(0, 0, 1, 1), Ok()));
            Assert.Equal(One + "Page", page.Name);
            Assert.Equal("P1", (string)page.Attribute("ID"));
            Assert.Equal(new[] { "Outline" }, page.Elements().Select(e => e.Name.LocalName));
            Assert.Null(page.Descendants().Attributes("selected").FirstOrDefault());
        }

        [Fact]
        public void No_decimal_line_when_text_has_approx()
        {
            var r = Ok();
            r.Answer = new SolverAnswer { Text = "x ≈ 0.347296", Decimal = "0.347296" };
            r.Notes.Clear();
            Assert.Equal(new[] { "x ≈ 0.347296", "Solved offline · verified" }, Texts(AnswerWriter.BuildXml("P1", Box, r)));
        }

        [Fact]
        public void No_decimal_line_without_decimal()
        {
            var r = Ok();
            r.Answer = new SolverAnswer { Text = "x = 6", Decimal = null };
            r.Notes.Clear();
            Assert.Equal(new[] { "x = 6", "Solved offline · verified" }, Texts(AnswerWriter.BuildXml("P1", Box, r)));
        }

        [Fact]
        public void Hidden_steps_mean_no_step_lines()
        {
            var lines = Texts(AnswerWriter.BuildXml("P1", Box, Ok()));
            Assert.Equal("x = −√2, x = √2", lines[0]);
            Assert.Equal(5 - 1, lines.Length);
        }

        [Fact]
        public void Escapes_html()
        {
            var r = Ok();
            r.Answer = new SolverAnswer { Text = "x < 2 & y > 3 ]]>" };
            var xml = AnswerWriter.BuildXml("P1", Box, r);
            Assert.Equal("x < 2 & y > 3 ]]>", Texts(xml)[0]);
            Assert.Contains("x &lt; 2 &amp; y &gt; 3", Cdata(xml)[0]);
        }

        [Fact]
        public void Answer_is_bold_and_16pt_source_is_11pt_grey()
        {
            var c = Cdata(AnswerWriter.BuildXml("P1", Box, Ok("Step")));
            Assert.Contains("font-size:14pt", c[0]);
            Assert.Contains("#1A1A1A", c[0]);
            Assert.Contains("font-weight:bold", c[1]);
            Assert.Contains("font-size:16pt", c[1]);
            Assert.DoesNotContain("bold", c[2]);
            Assert.Contains("font-size:11pt", c.Last());
            Assert.Contains("#555555", c.Last());
        }
    }
}
