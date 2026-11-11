using InkMath.AddIn;
using Xunit;

namespace InkMath.Tests
{
    public class ProtocolTests
    {
        [Fact]
        public void Request_json_uses_snake_case_and_omits_nulls()
        {
            var j = Protocol.ToJson(new SolverRequest { Id = "a", Latex = "3x-7=11", ShowSteps = false });
            Assert.Equal("{\"id\":\"a\",\"latex\":\"3x-7=11\",\"show_steps\":false}", j);
        }

        [Fact]
        public void Request_json_includes_set_optionals_in_order()
        {
            var j = Protocol.ToJson(new SolverRequest { Id = "a", Latex = "f(x)=x", Operation = "evaluate_at", Point = "2" });
            Assert.Equal("{\"id\":\"a\",\"latex\":\"f(x)=x\",\"operation\":\"evaluate_at\",\"point\":\"2\",\"show_steps\":true}", j);
        }

        [Fact]
        public void Control_line() =>
            Assert.Equal("{\"id\":\"a\",\"control\":\"stop\"}", Protocol.Control("a", "stop"));

        [Fact]
        public void Parses_ok_response_with_unicode()
        {
            var r = Protocol.Parse("{\"id\": \"a\", \"status\": \"ok\", \"operation\": \"solve\", \"variable\": \"x\", \"choices\": [\"solve\"], \"steps\": [\"Quadratic formula: a = 1, b = 0, c = −2\"], \"answer\": {\"latex\": \"x\", \"text\": \"x = −√2, x = √2\", \"decimal\": \"−1.41421, 1.41421\"}, \"notes\": [], \"verified\": true, \"source\": \"Solved offline · verified\", \"message\": \"\", \"ms\": 339}");
            Assert.Equal("x = −√2, x = √2", r.Answer.Text);
            Assert.Equal("−1.41421, 1.41421", r.Answer.Decimal);
            Assert.Equal("Quadratic formula: a = 1, b = 0, c = −2", r.Steps[0]);
            Assert.True(r.Verified);
            Assert.Equal(339, r.Ms);
            Assert.Equal("Solved offline · verified", r.Source);
        }

        [Fact]
        public void Parses_response_without_answer()
        {
            var r = Protocol.Parse("{\"id\":\"b\",\"status\":\"needs_operation\",\"choices\":[\"factor\",\"evaluate_at\"],\"answer\":null,\"message\":\"What should I do with this?\"}");
            Assert.Null(r.Answer);
            Assert.Empty(r.Steps);
            Assert.Empty(r.Notes);
            Assert.Equal(new[] { "factor", "evaluate_at" }, r.Choices);
            Assert.Equal("What should I do with this?", r.Message);
        }

        [Fact]
        public void Ready_line()
        {
            Assert.True(Protocol.IsReady("{\"ready\": true}"));
            Assert.False(Protocol.IsReady("{\"id\":\"a\"}"));
            Assert.False(Protocol.IsReady("not json"));
        }

        [Fact]
        public void Labels()
        {
            Assert.Equal("Evaluate at a point", OperationLabels.Label("evaluate_at"));
            Assert.Equal("Solve ODE", OperationLabels.Label("ode"));
            Assert.Equal("graph", OperationLabels.Label("graph"));
        }
    }
}
