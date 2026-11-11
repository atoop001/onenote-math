using InkMath.AddIn;
using Xunit;
using static InkMath.Tests.TestFiles;

namespace InkMath.Tests
{
    public class SelectionReaderTests
    {
        static string TypedPage(string cdata) => Fixture("selection_typed.xml").Replace("<![CDATA[3x-7=11]]>", "<![CDATA[" + cdata + "]]>");

        [Fact]
        public void Typed_text_selection()
        {
            var s = SelectionReader.Read(Fixture("selection_typed.xml"));
            Assert.Equal("3x-7=11", s.TypedText);
            Assert.Empty(s.Ink);
            Assert.Equal(new PageRect(36, 120, 200, 30), s.Bounds);
            Assert.False(s.IsEmpty);
        }

        [Fact]
        public void Ink_selection_unions_bounds_and_skips_unselected()
        {
            var s = SelectionReader.Read(Fixture("selection_ink.xml"));
            Assert.Equal(2, s.Ink.Count);
            Assert.Equal(new PageRect(40, 100, 120, 40), s.Bounds);
            Assert.Equal(new byte[] { 0, 0, 0 }, s.Ink[0].Isf);
            Assert.Equal(new PageRect(100, 110, 60, 30), s.Ink[1].Bounds);
        }

        [Fact]
        public void Ink_words_use_their_outline_bounds()
        {
            var s = SelectionReader.Read(Fixture("selection_inkword.xml"));
            Assert.Single(s.Ink);
            Assert.Equal(new PageRect(40, 230, 100, 30), s.Ink[0].Bounds);
            Assert.Equal(new PageRect(40, 230, 100, 30), s.Bounds);
        }

        [Fact]
        public void Caret_only_is_empty() => Assert.True(SelectionReader.Read(Fixture("selection_caret.xml")).IsEmpty);

        [Fact]
        public void Title_selection_is_ignored() => Assert.True(SelectionReader.Read(Fixture("selection_title.xml")).IsEmpty);

        [Fact]
        public void Html_in_typed_text_is_stripped() =>
            Assert.Equal("x < 2", SelectionReader.Read(TypedPage("<span style='font-weight:bold'>x &lt; 2</span>")).TypedText);

        [Fact]
        public void Page_id_is_read() => Assert.Equal("{PAGE-2}", SelectionReader.Read(Fixture("selection_ink.xml")).PageId);
    }
}
