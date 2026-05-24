// jobPilot interview prep template
// Invoked: typst compile interview_prep.typ out.pdf --input data=<path/to/data.yaml>

#let data = yaml(sys.inputs.at("data"))

#set page(paper: "us-letter", margin: (x: 1.25cm, y: 1.5cm))
#set text(size: 10.5pt)
#set par(leading: 0.55em)

// ── Header ───────────────────────────────────────────────────────
#align(center)[
  #text(size: 18pt, weight: "bold")[#data.at("job_title", default: "")]
  #linebreak()
  #text(size: 12pt, fill: luma(80))[#data.at("company", default: "")]
  #linebreak()
  #v(0.15em)
  #text(size: 10pt, fill: luma(120))[Interview Prep Guide]
]
#line(length: 100%, stroke: 0.5pt + luma(180))
#v(0.3em)

// ── Talking Points ───────────────────────────────────────────────
#let talking_points = data.at("talking_points", default: ())
#if talking_points.len() > 0 [
  == Key Talking Points

  #for pt in talking_points [
    #set text(size: 9.5pt)
    - #pt
  ]
  #v(0.4em)
]

// ── Gaps to Prepare For (Red Flags) ─────────────────────────────
#let red_flags = data.at("red_flags", default: ())
#if red_flags.len() > 0 [
  == Gaps to Prepare For

  #block(
    width: 100%,
    inset: 10pt,
    radius: 4pt,
    fill: rgb("#fff9e6"),
    stroke: 0.5pt + rgb("#e6c300"),
  )[
    #for flag in red_flags [
      #set text(size: 9.5pt, fill: rgb("#664d03"))
      - #flag
    ]
  ]
  #v(0.4em)
]

// ── STAR Stories ─────────────────────────────────────────────────
#let star_stories = data.at("star_stories", default: ())
#if star_stories.len() > 0 [
  == STAR Stories

  #for story in star_stories [
    #block(
      width: 100%,
      inset: 10pt,
      radius: 4pt,
      stroke: 0.5pt + luma(200),
      below: 8pt,
    )[
      #text(weight: "bold", size: 10pt)[#story.at("question", default: "")]
      #if story.at("resume_bullet", default: "") != "" [
        #linebreak()
        #text(size: 8.5pt, fill: luma(100), style: "italic")[From your resume: #story.at("resume_bullet", default: "")]
      ]
      #v(0.3em)
      #grid(
        columns: (auto, 1fr),
        column-gutter: 8pt,
        row-gutter: 6pt,
        text(weight: "bold", size: 8.5pt, fill: luma(100))[S],
        text(size: 9.5pt)[#story.at("situation", default: "")],
        text(weight: "bold", size: 8.5pt, fill: luma(100))[T],
        text(size: 9.5pt)[#story.at("task", default: "")],
        text(weight: "bold", size: 8.5pt, fill: luma(100))[A],
        text(size: 9.5pt)[#story.at("action", default: "")],
        text(weight: "bold", size: 8.5pt, fill: luma(100))[R],
        text(size: 9.5pt)[#story.at("result", default: "")],
      )
    ]
  ]
  #v(0.3em)
]

// ── Likely Questions ─────────────────────────────────────────────
#let likely_questions = data.at("likely_questions", default: ())
#if likely_questions.len() > 0 [
  == Likely Questions

  #for q in likely_questions [
    #if type(q) == str [
      #block(
        width: 100%,
        inset: 10pt,
        radius: 4pt,
        stroke: 0.5pt + luma(200),
        below: 8pt,
      )[
        #text(weight: "bold", size: 10pt)[#q]
      ]
    ] else [
      #block(
        width: 100%,
        inset: 10pt,
        radius: 4pt,
        stroke: 0.5pt + luma(200),
        below: 8pt,
      )[
        #text(weight: "bold", size: 10pt)[#q.at("question", default: "")]
        #linebreak()
        #v(0.15em)
        #text(size: 9.5pt)[#q.at("suggested_answer", default: "")]
        #if q.at("rationale", default: "") != "" [
          #linebreak()
          #v(0.1em)
          #text(size: 8.5pt, fill: luma(100), style: "italic")[Why: #q.at("rationale", default: "")]
        ]
      ]
    ]
  ]
]
