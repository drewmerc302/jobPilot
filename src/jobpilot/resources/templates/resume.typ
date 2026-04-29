// Generic resume template for jobPilot.
// Invoked by tailor.py: typst compile resume.typ out.pdf --input resume=<path/to/resume.yaml>
//
// TODO (Phase 2): flesh out full layout. This is the minimal scaffold to establish
// the correct invocation contract (sys.inputs / yaml()) before the FastAPI layer is built.

#let data = yaml(sys.inputs.at("resume"))

#set page(paper: "us-letter", margin: (x: 1.25cm, y: 1.5cm))
#set text(font: "Linux Libertine", size: 11pt)
#set heading(numbering: none)

// Name + contact
#align(center)[
  #text(size: 18pt, weight: "bold")[#data.at("name", default: "")]
  #linebreak()
  #text(size: 9pt, fill: luma(80))[
    #data.at("email", default: "")
    #if data.at("phone", default: "") != "" [ · #data.at("phone", default: "") ]
    #if data.at("location", default: "") != "" [ · #data.at("location", default: "") ]
  ]
]

#line(length: 100%, stroke: 0.5pt + luma(150))
#v(0.5em)

// Summary
#if data.at("summary", default: "") != "" [
  #text(size: 9pt)[#data.at("summary", default: "")]
  #v(0.5em)
]

// Experience
#if data.at("experience", default: ()).len() > 0 [
  == Experience

  #for exp in data.at("experience", default: ()) [
    #grid(
      columns: (1fr, auto),
      [*#exp.at("company", default: "")* — #exp.at("title", default: "")],
      [#text(size: 9pt, fill: luma(80))[#exp.at("dates", default: "")]],
    )
    #for bullet in exp.at("bullets", default: ()) [
      - #bullet
    ]
    #v(0.3em)
  ]
]

// Skills
#if data.at("skills", default: none) != none [
  == Skills

  #let skills = data.at("skills", default: ())
  #if type(skills) == array [
    #skills.join(", ")
  ] else [
    #for (cat, items) in skills [
      *#cat:* #items.join(", ") \
    ]
  ]
  #v(0.5em)
]

// Education
#if data.at("education", default: ()).len() > 0 [
  == Education

  #for edu in data.at("education", default: ()) [
    *#edu.at("school", default: "")* — #edu.at("degree", default: "")
    #if edu.at("year", default: "") != "" [ (#edu.at("year", default: "")) ]
    \
  ]
]
