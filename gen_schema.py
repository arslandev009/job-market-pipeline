from pathlib import Path

content = r'''# GBNF grammar for structured job-posting extraction.
#
# Loaded by llama.cpp's grammar-sampling feature so the model's token sampler is
# structurally *incapable* of producing anything except valid JSON matching this
# shape - no trailing commas, no wrong enum values, no explanatory prose before/
# after the JSON. See docs/PHASE5.md and docs/ARCHITECTURE.md section 5 for why this
# beats "prompt for JSON and hope."

root ::= "{" ws
  "\"seniority\":" ws seniority "," ws
  "\"remote_or_onsite\":" ws remote "," ws
  "\"salary_min\":" ws int_or_null "," ws
  "\"salary_max\":" ws int_or_null "," ws
  "\"location\":" ws string_or_null "," ws
  "\"required_skills\":" ws string_array
ws "}"

seniority ::= "\"intern\"" | "\"junior\"" | "\"mid\"" | "\"senior\"" | "\"lead\"" | "\"unknown\""
remote ::= "\"remote\"" | "\"onsite\"" | "\"hybrid\"" | "\"unknown\""

int_or_null ::= null | int
int ::= "-"? [0-9]+
null ::= "null"

string_or_null ::= null | string
string ::= "\"" char* "\""
char ::= [^"\\] | "\\" (["\\/bfnrt] | "u" [0-9a-fA-F]{4})

string_array ::= "[" ws (string (ws "," ws string)*)? ws "]"

ws ::= [ \t\n]*
'''

path = Path("src/llm_extraction/schema.gbnf")
path.write_text(content, encoding="utf-8", newline="\n")
print("Wrote:", path.resolve())
print("First 20 bytes:", repr(path.read_bytes()[:20]))
print("Length:", len(content), "chars")