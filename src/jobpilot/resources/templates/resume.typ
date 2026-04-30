// jobPilot resume template
// Invoked: typst compile resume.typ out.pdf --input resume=<path/to/resume.yaml>

#let data = yaml(sys.inputs.at("resume"))

#set page(paper: "us-letter", margin: (x: 1.25cm, y: 1.5cm))
#set text(size: 10.5pt)
#set par(leading: 0.55em)

// ── Header ───────────────────────────────────────────────────────
#align(center)[
  #text(size: 18pt, weight: "bold")[#data.at("name", default: "")]
  #linebreak()
  #text(size: 9pt, fill: luma(80))[
    #let parts = ()
    #if data.at("email", default: "") != "" { parts.push(data.at("email")) }
    #if data.at("phone", default: "") != "" { parts.push(data.at("phone")) }
    #if data.at("location", default: "") != "" { parts.push(data.at("location")) }
    #if data.at("linkedin", default: "") != "" { parts.push(data.at("linkedin")) }
    #parts.join("  ·  ")
  ]
]
#line(length: 100%, stroke: 0.5pt + luma(180))
#v(0.3em)

// ── Summary ──────────────────────────────────────────────────────
#if data.at("summary", default: "") != "" [
  #text(size: 9.5pt)[#data.at("summary")]
  #v(0.4em)
  #line(length: 100%, stroke: 0.3pt + luma(200))
  #v(0.3em)
]

// ── Experience ───────────────────────────────────────────────────
#let experience = data.at("experience", default: ())
#if experience.len() > 0 [
  == Experience

  #for exp in experience [
    #let positions = exp.at("positions", default: ())
    #for pos in positions [
      #grid(
        columns: (1fr, auto),
        gutter: 4pt,
        [*#exp.at("company", default: "")* — #pos.at("title", default: "")],
        [#text(size: 9pt, fill: luma(80))[#pos.at("dates", default: "")]],
      )
      #if exp.at("location", default: "") != "" [
        #text(size: 9pt, fill: luma(100))[#exp.at("location", default: "")]
        #v(0.1em)
      ]
      #for bullet in pos.at("achievements", default: ()) [
        #set text(size: 9.5pt)
        - #bullet
      ]
      #v(0.25em)
    ]
  ]
]

// ── Skills ───────────────────────────────────────────────────────
#let skills = data.at("skills", default: none)
#if skills != none [
  == Skills

  #if type(skills) == array [
    #text(size: 9.5pt)[#skills.join(", ")]
  ] else [
    #for (cat, items) in skills [
      #text(size: 9.5pt)[*#cat:* #items.join(", ")]
      \
    ]
  ]
  #v(0.3em)
]

// ── Education ────────────────────────────────────────────────────
#let education = data.at("education", default: ())
#if education.len() > 0 [
  == Education

  #for edu in education [
    #grid(
      columns: (1fr, auto),
      gutter: 4pt,
      [*#edu.at("school", default: "")* — #edu.at("degree", default: "")],
      [#text(size: 9pt, fill: luma(80))[#edu.at("year", default: "")]],
    )
  ]
]
