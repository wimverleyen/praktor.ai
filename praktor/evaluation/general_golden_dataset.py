"""
Golden dataset for non-clinical (general) agents.

3 samples per agent type × 7 agents = 21 samples total.
Each sample provides:
  • input_data   — dict of fields to pass to the agent
  • reference_output — expert-written ideal response
  • context      — human-readable task description used by the judge
  • notes        — what makes this reference output good

Sample size note
────────────────
3 samples per agent is a bootstrap — adequate for catching obvious regressions
(~50% power at δ=1.5 pts). Target 10 samples per agent for 80% power.
Use `python -m praktor eval --detail` to see per-sample scores and expand the
dataset where σ is high.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GeneralGoldenSample:
    sample_id: str
    agent_type: str
    input_data: dict           # fields to pass to Agent.run()
    reference_output: str      # ideal response written by a human expert
    context: str               # task description for the judge (member_context)
    notes: str = ""            # what distinguishes a high-quality response


# ---------------------------------------------------------------------------
# cover_letter  (G-CL-001 – G-CL-003)
# ---------------------------------------------------------------------------

_COVER_LETTER_SAMPLES = [
    GeneralGoldenSample(
        sample_id="G-CL-001",
        agent_type="cover_letter",
        input_data={
            "job_title": "VP of Engineering",
            "company": "Acme AI",
            "job_description": (
                "We are looking for a VP of Engineering to lead our 40-person engineering org. "
                "You will own the technical roadmap, manage directors, and partner with product "
                "to ship high-quality AI features. Requires 10+ years engineering leadership, "
                "experience scaling distributed systems, and a track record of hiring great teams."
            ),
        },
        reference_output=(
            "Dear Hiring Team at Acme AI,\n\n"
            "At my previous company I scaled an engineering org from 12 to 85 engineers while "
            "shipping three major platform rewrites on schedule — that kind of structured growth "
            "is exactly what you are describing for the VP of Engineering role.\n\n"
            "Over the past decade I have led teams building distributed data pipelines processing "
            "4 billion events per day, reduced deployment time from two weeks to under 90 minutes "
            "through progressive CI/CD adoption, and hired 40+ engineers with a 91% two-year "
            "retention rate by investing early in engineering culture and career ladders.\n\n"
            "Acme AI's focus on AI-native products is compelling. I have hands-on experience "
            "leading the technical integration of LLM services into production at scale, including "
            "the latency, cost, and reliability tradeoffs that matter most when AI is on the "
            "critical path. I would welcome the chance to discuss how my background maps to your "
            "roadmap. Thank you for your consideration.\n\n"
            "Sincerely,\n[Candidate Name]"
        ),
        context=(
            "Task: write a compelling cover letter for the VP of Engineering role at Acme AI. "
            "The job requires 10+ years engineering leadership, distributed systems experience, "
            "and strong hiring track record. The letter should lead with a concrete achievement, "
            "mirror the job description's language, and end with a confident call to action. "
            "Target length: 3 focused paragraphs."
        ),
        notes=(
            "Leads with a concrete metric (12 → 85 engineers). "
            "Mirrors JD language (distributed systems, hiring, technical roadmap). "
            "AI-specific paragraph shows domain fit. Exactly 3 paragraphs. No filler."
        ),
    ),

    GeneralGoldenSample(
        sample_id="G-CL-002",
        agent_type="cover_letter",
        input_data={
            "job_title": "Senior Data Scientist",
            "company": "HealthMetrics",
            "job_description": (
                "Join our data science team to build predictive models for patient risk "
                "stratification. You will work with EHR data, develop ML pipelines in Python, "
                "and collaborate with clinical teams. Requires PhD or 5+ years industry experience, "
                "strong statistics background, and healthcare domain knowledge preferred."
            ),
        },
        reference_output=(
            "Dear HealthMetrics Team,\n\n"
            "My predictive model for 30-day hospital readmission — deployed across 14 hospitals "
            "and now flagging 38% of at-risk patients before discharge — is the kind of impact "
            "I am eager to bring to your patient risk stratification work.\n\n"
            "I have spent five years building production ML pipelines on EHR data (Epic, Cerner) "
            "in Python and PySpark, with a focus on survival models, gradient boosting, and "
            "causal inference to move beyond correlation into actionable clinical guidance. "
            "Working directly alongside hospitalists and care managers taught me to frame model "
            "outputs in clinical terms that drive behavior change, not just AUC improvements.\n\n"
            "HealthMetrics' mission to make risk visible before crises occur is exactly the "
            "problem I find most meaningful. I would love to walk through my pipeline architecture "
            "and discuss where my experience fits your roadmap.\n\n"
            "Best regards,\n[Candidate Name]"
        ),
        context=(
            "Task: write a cover letter for a Senior Data Scientist role at HealthMetrics focused "
            "on patient risk stratification using EHR data. Should demonstrate healthcare ML "
            "experience, Python/statistics skills, and clinical collaboration. 3 paragraphs."
        ),
        notes=(
            "Opens with a specific deployed model metric. "
            "Names EHR platforms (Epic, Cerner). Mentions clinical collaboration concretely. "
            "Connects to company mission without flattery."
        ),
    ),

    GeneralGoldenSample(
        sample_id="G-CL-003",
        agent_type="cover_letter",
        input_data={
            "job_title": "Head of Product",
            "company": "Finova",
            "job_description": (
                "Lead product strategy for our B2B fintech platform serving 500 SMBs. "
                "Own the roadmap, manage a team of 5 PMs, and work closely with sales and "
                "engineering. Looking for someone who can balance short-term revenue impact "
                "with long-term platform investments. 7+ years product management required."
            ),
        },
        reference_output=(
            "Dear Finova Team,\n\n"
            "When I re-sequenced our SMB onboarding flow based on three weeks of customer "
            "interviews, average time-to-first-value dropped from 18 days to 4 — and ARR "
            "expansion in that cohort grew 22% year-over-year. That balance of short-term "
            "revenue pull and long-term platform thinking is precisely what drew me to this role.\n\n"
            "Over 8 years in B2B product at two fintech companies, I have owned roadmaps from "
            "zero to $40M ARR, built and managed PM teams of up to 7, and run the quarterly "
            "planning process that aligned sales, engineering, and finance on a single shared "
            "backlog. I am comfortable in the room when a major customer escalates and comfortable "
            "in the data when a metric moves unexpectedly.\n\n"
            "Finova's focus on the underserved SMB segment resonates with me — there is real "
            "complexity in serving customers with limited ops bandwidth, and I find that "
            "constraint clarifying. I would welcome the chance to discuss your roadmap priorities.\n\n"
            "Best,\n[Candidate Name]"
        ),
        context=(
            "Task: cover letter for Head of Product at Finova, B2B fintech serving SMBs. "
            "Must show roadmap ownership, PM team management, revenue impact, and the "
            "short-term/long-term balance the JD emphasizes. 3 focused paragraphs."
        ),
        notes=(
            "Opens with a tight story (onboarding flow → specific ARR delta). "
            "Mirrors JD language (short-term/long-term). "
            "Acknowledges SMB-specific constraint as a strength signal."
        ),
    ),
]


# ---------------------------------------------------------------------------
# job_application  (G-JA-001 – G-JA-003)
# ---------------------------------------------------------------------------

_JOB_APPLICATION_SAMPLES = [
    GeneralGoldenSample(
        sample_id="G-JA-001",
        agent_type="job_application",
        input_data={
            "job_title": "Machine Learning Engineer",
            "company": "DeepScale",
            "job_description": (
                "Build and productionize ML models for autonomous vehicle perception. "
                "Work with PyTorch, CUDA, and large-scale data pipelines. "
                "Strong Python and distributed computing required. 3+ years ML experience."
            ),
        },
        reference_output=(
            "APPLICATION: Machine Learning Engineer — DeepScale\n\n"
            "WHY THIS ROLE:\n"
            "Autonomous perception is one of the hardest real-time ML problems: strict latency "
            "budgets, sensor fusion, and safety-critical constraints that eliminate the usual "
            "tolerance for model drift. That combination of engineering rigor and research "
            "challenge is where I do my best work.\n\n"
            "RELEVANT EXPERIENCE:\n"
            "- 4 years building production PyTorch models for computer vision (object detection, "
            "  semantic segmentation) with inference optimized for edge deployment via TensorRT.\n"
            "- Built distributed training pipelines on 256-GPU clusters using PyTorch DDP; "
            "  reduced training wall-clock time by 3.1× through gradient checkpointing and "
            "  mixed-precision.\n"
            "- Proficient in CUDA kernel optimization for custom attention operators.\n\n"
            "KEY MATCH:\n"
            "Your requirement for large-scale data pipeline experience maps directly to my work "
            "on streaming ingestion of 40TB/day from 8 sensor modalities."
        ),
        context=(
            "Task: write a job application for ML Engineer at DeepScale (autonomous vehicles). "
            "Must show PyTorch, CUDA, distributed training, and production ML experience. "
            "Should be structured with clear sections and concrete metrics."
        ),
        notes=(
            "Structured format (WHY / EXPERIENCE / MATCH). "
            "Concrete numbers (256 GPUs, 3.1× speedup, 40TB/day). "
            "Mirrors JD keywords precisely."
        ),
    ),

    GeneralGoldenSample(
        sample_id="G-JA-002",
        agent_type="job_application",
        input_data={
            "job_title": "Data Engineering Manager",
            "company": "Pulse Analytics",
            "job_description": (
                "Lead a team of 6 data engineers building our real-time analytics platform. "
                "Own the data infrastructure roadmap and partner with analytics and product. "
                "Requires Spark, Kafka, Snowflake expertise and 2+ years managing engineers."
            ),
        },
        reference_output=(
            "APPLICATION: Data Engineering Manager — Pulse Analytics\n\n"
            "WHY THIS ROLE:\n"
            "Building data infrastructure that analysts and PMs trust without thinking about it "
            "is the goal I optimize for. Real-time platforms are particularly interesting because "
            "the failure modes are visible immediately — latency spikes show up in dashboards "
            "within seconds, which sharpens the feedback loop for the engineering team.\n\n"
            "RELEVANT EXPERIENCE:\n"
            "- 3 years managing a 5-person data engineering team; grew it to 8 with zero "
            "  involuntary attrition by building structured on-call rotations and technical "
            "  growth paths.\n"
            "- Designed and shipped a Kafka → Spark Structured Streaming → Snowflake pipeline "
            "  handling 2.5M events/min with p99 latency under 800ms.\n"
            "- Owned data infrastructure roadmap planning with quarterly OKRs, reviewed quarterly "
            "  by CPO and CTO.\n\n"
            "KEY MATCH:\n"
            "Your Spark + Kafka + Snowflake stack is my primary toolchain. "
            "I can contribute day one without a ramp-up on the platform."
        ),
        context=(
            "Task: job application for Data Engineering Manager at Pulse Analytics. "
            "Needs to demonstrate team management, real-time data expertise "
            "(Spark/Kafka/Snowflake), and roadmap ownership. Concrete metrics expected."
        ),
        notes=(
            "Shows people management metric (zero attrition). "
            "Names the exact stack from the JD. "
            "Latency numbers make the technical claim specific."
        ),
    ),

    GeneralGoldenSample(
        sample_id="G-JA-003",
        agent_type="job_application",
        input_data={
            "job_title": "AI Product Manager",
            "company": "ClearMind",
            "job_description": (
                "Define and ship AI features for our mental health platform. "
                "Work with researchers, engineers, and clinical advisors. "
                "Requires 5+ years PM experience, understanding of ML systems, "
                "and sensitivity to the mental health context."
            ),
        },
        reference_output=(
            "APPLICATION: AI Product Manager — ClearMind\n\n"
            "WHY THIS ROLE:\n"
            "AI in mental health sits at an unusual intersection: the upside of personalization "
            "is real, and so is the responsibility not to harm a vulnerable user population. "
            "That tension — shipping fast enough to matter, carefully enough not to harm — is "
            "exactly the kind of product challenge I find most meaningful.\n\n"
            "RELEVANT EXPERIENCE:\n"
            "- 6 years product management, including 3 years at a digital health company where "
            "  I worked directly with clinical psychologists to define safe and effective AI "
            "  feature boundaries.\n"
            "- Shipped a mood-tracking ML feature used by 120K monthly active users; worked with "
            "  the research team to validate that the model did not introduce systematic bias "
            "  for underrepresented user groups.\n"
            "- Comfortable reading ML model cards, interpreting confusion matrices, and "
            "  translating technical risk to clinical and executive stakeholders.\n\n"
            "KEY MATCH:\n"
            "Clinical advisor collaboration is something I have done directly — "
            "I know how to move fast while keeping the clinical review loop intact."
        ),
        context=(
            "Task: job application for AI PM role at ClearMind (mental health platform). "
            "Must show sensitivity to clinical context, ML literacy, stakeholder management, "
            "and concrete PM experience. Structured format with metrics."
        ),
        notes=(
            "Addresses the clinical sensitivity directly in the WHY section. "
            "Shows ML literacy without overselling technical depth. "
            "Gives a real user-scale metric."
        ),
    ),
]


# ---------------------------------------------------------------------------
# job_interview  (G-JI-001 – G-JI-003)
# ---------------------------------------------------------------------------

_JOB_INTERVIEW_SAMPLES = [
    GeneralGoldenSample(
        sample_id="G-JI-001",
        agent_type="job_interview",
        input_data={
            "search": "Tell me about yourself",
            "content": (
                "Candidate background: 7 years in data engineering at fintech companies. "
                "Built data pipelines, led a team of 4, recently led a migration from Hadoop "
                "to Snowflake. Interviewing for a Senior Data Engineer role."
            ),
        },
        reference_output=(
            "INTERVIEW ANSWER — Tell me about yourself\n\n"
            "I have spent seven years in data engineering in fintech, starting as an individual "
            "contributor building ETL pipelines and gradually taking on leadership — I now run "
            "a team of four.\n\n"
            "The project I am most proud of is the migration we completed last year from a "
            "Hadoop-based warehouse to Snowflake. That was a two-year effort: we had to move "
            "about 200 production pipelines without downtime for the analytics teams, and we "
            "ended up 40% under budget because we automated the schema migration step that "
            "everyone expected to be manual.\n\n"
            "I am looking for a senior role where I can continue to work at scale and also "
            "keep growing the technical mentorship side — that is the part of leadership I "
            "find most energizing. This role looked like a strong fit on both dimensions.\n\n"
            "COACHING NOTES:\n"
            "- Lead with trajectory, not just a chronology of jobs.\n"
            "- Anchor on one concrete project — the Snowflake migration — with a real metric.\n"
            "- End by connecting your motivation to this specific role."
        ),
        context=(
            "Task: prepare a strong answer to 'Tell me about yourself' for a Senior Data "
            "Engineer interview. Candidate has 7 years fintech data engineering experience, "
            "team lead, led Hadoop-to-Snowflake migration. Answer should include coaching notes."
        ),
        notes=(
            "Trajectory narrative (IC → lead). Concrete project with a real metric (40% under budget). "
            "Ends with motivation signal. Coaching notes add meta-value."
        ),
    ),

    GeneralGoldenSample(
        sample_id="G-JI-002",
        agent_type="job_interview",
        input_data={
            "search": "What is your greatest weakness?",
            "content": (
                "Candidate background: senior product manager, strong on strategy and vision, "
                "sometimes struggles to delegate execution details to junior PMs. "
                "Aware of it; has been working on structured delegation frameworks."
            ),
        },
        reference_output=(
            "INTERVIEW ANSWER — What is your greatest weakness?\n\n"
            "My genuine weakness is letting go of execution detail when I hand off to a junior PM. "
            "I tend to have a sharp mental model of how something should work, and early in my "
            "career I would hold on to tasks longer than I should — not out of mistrust, but "
            "because I had not yet built the trust that comes from clear, structured handoffs.\n\n"
            "What I have done about it: over the past 18 months I built a handoff template I "
            "use for every project I delegate — it covers context, success criteria, decision "
            "boundaries, and the cadence for check-ins. The result is that my two junior PMs "
            "now own three features end-to-end that I would previously have kept. They both told "
            "me it was the clearest brief they had received from anyone on the team.\n\n"
            "It is still something I pay attention to. But I am at the point where I catch "
            "myself early, and the structured handoff process makes it a system problem, "
            "not a willpower problem.\n\n"
            "COACHING NOTES:\n"
            "- Genuine weakness, not a disguised strength. Interviewers see through 'I work too hard.'\n"
            "- Concrete mitigation (handoff template) with a real outcome.\n"
            "- End showing self-awareness, not resolution."
        ),
        context=(
            "Task: prepare a strong answer to 'greatest weakness' for a senior PM interview. "
            "The real weakness is difficulty delegating execution detail. "
            "Answer must be genuine, show concrete mitigation, and include coaching notes."
        ),
        notes=(
            "Real weakness, not humblebrag. Specific mitigation (template + cadence). "
            "Outcome from junior PMs validates the fix. Coaching note explains why."
        ),
    ),

    GeneralGoldenSample(
        sample_id="G-JI-003",
        agent_type="job_interview",
        input_data={
            "search": "Describe a time you failed",
            "content": (
                "Candidate background: engineering manager who launched a feature that had to be "
                "rolled back after 48 hours due to a performance regression. Team caught it via "
                "monitoring; no user data was lost. Post-mortem was run."
            ),
        },
        reference_output=(
            "INTERVIEW ANSWER — Describe a time you failed\n\n"
            "Eighteen months ago I led a feature launch that we had to roll back 48 hours after "
            "release. We shipped a new real-time aggregation layer, and under production load "
            "patterns — which differed from our staging environment in one key way we had missed — "
            "p99 latency spiked from 120ms to 4.2 seconds. Monitoring caught it, no user data "
            "was affected, but it was still a clear failure of our pre-release process.\n\n"
            "My specific mistake: I accepted an approximation in the load test setup ("
            "'close enough') that I should have pushed back on. The team was under timeline "
            "pressure, and I did not fight hard enough for the extra two days to fix the test "
            "environment gap. That tradeoff was mine to make — and it was the wrong call.\n\n"
            "The post-mortem produced two structural fixes: a production-equivalent staging "
            "environment (now standard for all backend services) and a checklist item that "
            "explicitly requires any 'close enough' approximations to be documented and signed "
            "off by the EM before a release gate. We have shipped 11 backend features since "
            "without a rollback.\n\n"
            "COACHING NOTES:\n"
            "- Take clear personal ownership — do not diffuse blame to 'the team' or 'the process.'\n"
            "- Show the structural fix, not just the lesson. Interviewers want to see systems thinking.\n"
            "- The post-metric (11 features, 0 rollbacks) closes the loop."
        ),
        context=(
            "Task: prepare a 'time you failed' answer for an engineering manager interview. "
            "The failure: a feature rollback 48 hours post-launch due to performance regression. "
            "Answer needs clear personal ownership, root cause, structural fix, and coaching notes."
        ),
        notes=(
            "Specific numbers (120ms → 4.2s, 48 hours). Personal ownership of the bad tradeoff. "
            "Structural fix, not just 'I learned'. Post-metric validates the fix."
        ),
    ),
]


# ---------------------------------------------------------------------------
# keywords_extraction  (G-KE-001 – G-KE-003)
# ---------------------------------------------------------------------------

_KEYWORDS_EXTRACTION_SAMPLES = [
    GeneralGoldenSample(
        sample_id="G-KE-001",
        agent_type="keywords_extraction",
        input_data={
            "job_title": "Staff Machine Learning Engineer",
            "company": "Orbital AI",
            "job_description": (
                "Design and deploy large-scale ML systems for recommendation and ranking. "
                "Lead technical design reviews, mentor senior engineers, and define ML "
                "platform standards. Requires expertise in PyTorch, distributed training, "
                "feature stores, A/B testing, and production model serving."
            ),
            "resume": (
                "5 years building ranking models at scale. Led design of a two-tower retrieval "
                "system (PyTorch, FAISS) serving 10M queries/day. Mentor 3 engineers. "
                "Experience with Feast feature store, online/offline serving, and Kubernetes."
            ),
        },
        reference_output=(
            "KEYWORD ANALYSIS — Staff ML Engineer / Orbital AI\n\n"
            "PRIORITY KEYWORDS (appear in JD, match your resume):\n"
            "  PyTorch, distributed training, recommendation/ranking, production model serving,\n"
            "  technical leadership, mentoring\n\n"
            "GAP KEYWORDS (in JD, NOT in your resume — add where honest):\n"
            "  A/B testing, feature store standards (you have Feast but not 'feature store "
            "  standards' language), ML platform ownership\n\n"
            "RESUME KEYWORDS TO SURFACE MORE PROMINENTLY:\n"
            "  Two-tower retrieval (highly specific, differentiated)\n"
            "  10M queries/day (scale signal — lead with this)\n"
            "  Kubernetes (operational credibility)\n\n"
            "ATS RISK:\n"
            "  Your resume uses 'retrieval system' — JD uses 'recommendation and ranking.'\n"
            "  Mirror the JD language in at least one bullet to pass ATS filters.\n\n"
            "RECOMMENDED ADDITIONS TO RESUME SUMMARY:\n"
            "  'Staff-level ML engineer with expertise in PyTorch-based recommendation and "
            "  ranking systems, production model serving at 10M+ QPS, and A/B-driven model "
            "  iteration cycles.'"
        ),
        context=(
            "Task: extract and analyze keywords from a Staff ML Engineer job description at "
            "Orbital AI, matched against the candidate's resume. Output should identify "
            "priority keywords (matched), gap keywords (unmatched), ATS risks, and "
            "a recommended resume summary update."
        ),
        notes=(
            "Categorizes by match state, not just lists. "
            "ATS risk is a concrete, actionable insight. "
            "Recommended summary is ready-to-paste."
        ),
    ),

    GeneralGoldenSample(
        sample_id="G-KE-002",
        agent_type="keywords_extraction",
        input_data={
            "job_title": "Head of Data Science",
            "company": "RetailOS",
            "job_description": (
                "Lead our data science org (12 people) to drive revenue through pricing, "
                "demand forecasting, and personalization. Partner with the C-suite on "
                "analytics strategy. Requires 8+ years DS experience, people leadership, "
                "and strong business acumen. SQL, Python, causal inference a plus."
            ),
            "resume": (
                "Director of Data Science, 10 years experience. Led team of 8. "
                "Built demand forecasting models (XGBoost) that reduced inventory waste 18%. "
                "Presented to CEO quarterly. Python, SQL, R, A/B testing."
            ),
        },
        reference_output=(
            "KEYWORD ANALYSIS — Head of Data Science / RetailOS\n\n"
            "PRIORITY KEYWORDS (strong match):\n"
            "  Data science leadership, people leadership, demand forecasting, Python, SQL,\n"
            "  C-suite partnership (your 'presented to CEO' maps here), business acumen\n\n"
            "GAP KEYWORDS (in JD, weaker in your resume):\n"
            "  Pricing models (you have forecasting but not pricing — add if you have it)\n"
            "  Personalization (not mentioned in your resume)\n"
            "  Causal inference (listed as 'a plus' in JD — high signal if you have it)\n\n"
            "STRONG DIFFERENTIATORS TO AMPLIFY:\n"
            "  18% inventory waste reduction (revenue impact — this is the language the JD wants)\n"
            "  Team size: you managed 8, they have 12 — frame as 'grew team' to close the gap\n\n"
            "ATS RISK:\n"
            "  'Director of Data Science' vs 'Head of Data Science' — add 'Head of DS' "
            "  or 'DS org leadership' to your summary.\n\n"
            "RECOMMENDED RESUME SUMMARY UPDATE:\n"
            "  'Head of Data Science with 10 years experience leading DS orgs (8 direct reports) "
            "  to drive revenue through demand forecasting, pricing, and personalization. "
            "  Delivered 18% inventory waste reduction. C-suite analytics partner.'"
        ),
        context=(
            "Task: keyword extraction for Head of DS role at RetailOS matched against candidate "
            "resume. Identify matched/gap keywords, differentiators, ATS risks, and provide "
            "a ready-to-use updated resume summary."
        ),
        notes=(
            "Flags pricing/personalization gap explicitly. Causal inference is called out as "
            "a high-signal gap. Team size delta addressed directly."
        ),
    ),

    GeneralGoldenSample(
        sample_id="G-KE-003",
        agent_type="keywords_extraction",
        input_data={
            "job_title": "AI Safety Researcher",
            "company": "Sentinel Labs",
            "job_description": (
                "Research and implement safety techniques for large language models including "
                "RLHF, constitutional AI, red-teaming, and interpretability. Publish and "
                "collaborate with external researchers. PhD preferred; strong ML theory required."
            ),
            "resume": (
                "PhD in ML (NeurIPS 2022 paper on reward model calibration). "
                "2 years at AI lab working on alignment. Red-teaming experience. "
                "Published 4 papers. Python, JAX, theoretical ML background."
            ),
        },
        reference_output=(
            "KEYWORD ANALYSIS — AI Safety Researcher / Sentinel Labs\n\n"
            "PRIORITY KEYWORDS (strong match):\n"
            "  RLHF (your reward model calibration paper maps here directly),\n"
            "  red-teaming, ML theory, PhD, publication record, Python\n\n"
            "GAP KEYWORDS:\n"
            "  Constitutional AI (Anthropic-specific term — clarify if your alignment work "
            "  covers this; if not, frame related work carefully)\n"
            "  Interpretability (not mentioned in your resume — add mechanistic interpretability "
            "  exposure if any)\n"
            "  External collaboration (highlight co-authors and collaborator orgs from papers)\n\n"
            "STRONG DIFFERENTIATORS:\n"
            "  NeurIPS 2022 paper on reward model calibration — this is highly specific to "
            "  RLHF safety research. Lead with it by name in the summary.\n"
            "  JAX experience signals alignment-lab-style compute environment familiarity.\n\n"
            "ATS RISK:\n"
            "  'Alignment' is your framing; JD uses 'AI safety.' Use both in your summary.\n\n"
            "RECOMMENDED SUMMARY:\n"
            "  'AI safety researcher (PhD) with 2 years at an AI alignment lab, "
            "  NeurIPS 2022 publication on RLHF reward model calibration, "
            "  and hands-on red-teaming experience. Published 4 papers; "
            "  active collaborator across research orgs.'"
        ),
        context=(
            "Task: keyword extraction for AI Safety Researcher at Sentinel Labs against a "
            "strong-match PhD candidate resume. Identify constitutional AI gap, "
            "highlight RLHF-alignment bridge, flag ATS 'safety vs alignment' risk."
        ),
        notes=(
            "Handles the 'constitutional AI' term carefully (Anthropic-specific). "
            "Surfaces JAX as lab-culture signal. 'Alignment vs AI safety' ATS risk is real."
        ),
    ),
]


# ---------------------------------------------------------------------------
# message  (G-MSG-001 – G-MSG-003)
# ---------------------------------------------------------------------------

_MESSAGE_SAMPLES = [
    GeneralGoldenSample(
        sample_id="G-MSG-001",
        agent_type="message",
        input_data={
            "topic": "team missed a quarterly OKR due to scope creep and should reset priorities",
            "emotion": "direct and accountable",
        },
        reference_output=(
            "Team,\n\n"
            "We missed our Q2 OKR on the data pipeline reliability target, and I want to be "
            "direct about why: we took on three unplanned requests in May that collectively "
            "consumed about 40% of our sprint capacity. The requests were reasonable individually "
            "— the problem was that we did not say no clearly enough, including me.\n\n"
            "Here is what we are doing differently in Q3: any new request above two story points "
            "goes through a scope gate that I will personally approve. We are also re-calibrating "
            "the reliability OKR to a number we can hit given actual staffing, not optimistic "
            "assumptions.\n\n"
            "I will share the updated OKR draft by Thursday for your input before we finalize. "
            "Thank you for staying focused despite the noise this quarter.\n\n"
            "[Name]"
        ),
        context=(
            "Task: write a direct, accountable message to a team about missing a quarterly OKR "
            "due to scope creep. Should acknowledge the miss clearly, explain the root cause, "
            "and outline the concrete changes for next quarter. Tone: direct and accountable."
        ),
        notes=(
            "Names the root cause (scope creep + failure to say no). "
            "Concrete fix (scope gate). Timeline given (Thursday). "
            "No defensiveness, no victim language."
        ),
    ),

    GeneralGoldenSample(
        sample_id="G-MSG-002",
        agent_type="message",
        input_data={
            "topic": "announcing a new AI strategy pivot to the broader company",
            "emotion": "inspiring and clear",
        },
        reference_output=(
            "Team,\n\n"
            "Starting this quarter, we are making AI the primary lens through which every "
            "product decision gets evaluated. This is not an experiment — it is a strategic "
            "commitment that will change how we build, what we ship, and how fast we move.\n\n"
            "Practically, this means three things in the next 90 days: every new product feature "
            "proposal will include an 'AI-first alternative' analysis; our two most senior "
            "engineers will move to full-time AI infrastructure; and we will run our first "
            "customer pilot of the AI-assisted workflow by the end of Q3.\n\n"
            "I know pivots create uncertainty. I will hold an all-hands on Friday at 2pm to "
            "answer questions directly. If you have concerns before then, my calendar is open.\n\n"
            "[Name]"
        ),
        context=(
            "Task: write an inspiring and clear company-wide message announcing an AI strategy "
            "pivot. Should explain the commitment level, give concrete 90-day actions, "
            "and address uncertainty directly. Professional executive tone."
        ),
        notes=(
            "Opens with a commitment statement, not a question. "
            "Three concrete 90-day actions make it tangible. "
            "Acknowledges uncertainty and offers a channel."
        ),
    ),

    GeneralGoldenSample(
        sample_id="G-MSG-003",
        agent_type="message",
        input_data={
            "topic": "congratulating a peer on a successful product launch after a difficult project",
            "emotion": "warm and genuine",
        },
        reference_output=(
            "Congrats on shipping Orion — watching that launch come together after the "
            "infrastructure issues in March was genuinely impressive.\n\n"
            "What stood out to me was how you kept the team aligned when the timeline slipped. "
            "You did not sugarcoat it, you did not panic — you just kept running clear stand-ups "
            "and making fast calls. That kind of calm under real pressure is harder than it looks.\n\n"
            "Enjoy the moment. You earned it.\n\n"
            "[Name]"
        ),
        context=(
            "Task: write a warm and genuine congratulations message to a peer on a difficult "
            "product launch. Should feel personal and specific (not generic), reference the "
            "difficulty, and highlight something specific the person did well."
        ),
        notes=(
            "References the specific difficulty (infrastructure issues in March). "
            "Calls out a specific behavior (clear stand-ups, fast calls). "
            "Short and genuine — not performative."
        ),
    ),
]


# ---------------------------------------------------------------------------
# search  (G-SR-001 – G-SR-003)
# ---------------------------------------------------------------------------

_SEARCH_SAMPLES = [
    GeneralGoldenSample(
        sample_id="G-SR-001",
        agent_type="search",
        input_data={
            "search": "What are the best practices for deploying LLMs in production?",
            "content": (
                "Context: engineering team is moving from prototype to production for a "
                "customer-facing LLM feature. Main concerns: latency, cost, reliability, "
                "and prompt injection security."
            ),
        },
        reference_output=(
            "LLM PRODUCTION DEPLOYMENT — KEY PRACTICES\n\n"
            "LATENCY\n"
            "- Stream responses (SSE/WebSocket) so users see output in <500ms even for "
            "  long generations.\n"
            "- Cache deterministic requests (temperature=0) with a semantic hash key; "
            "  expect 20-40% hit rate on typical workloads.\n"
            "- Run batching for offline/async paths; avoid it for interactive flows.\n\n"
            "COST\n"
            "- Set max_tokens per request type; open-ended generation burns 10× more "
            "  than structured output.\n"
            "- Use prompt caching APIs (Anthropic, OpenAI) for static system prompts — "
            "  typical 60-80% cost reduction on cached tokens.\n"
            "- Monitor cost/request by agent type; outliers usually indicate a broken "
            "  stop sequence or runaway loop.\n\n"
            "RELIABILITY\n"
            "- Implement retry with exponential backoff (max 3 retries, jitter) for 429/503.\n"
            "- Circuit breaker with fallback message if the model endpoint is down > 5s.\n"
            "- Log every prompt + completion for debugging; store for ≥30 days.\n\n"
            "PROMPT INJECTION\n"
            "- Treat all user input as untrusted: sanitize before interpolation, use "
            "  structured output schemas to limit what the model can 'say.'\n"
            "- Separate system prompt from user content structurally (not just by position).\n"
            "- Red-team your prompts before launch; injection patterns are easy to find "
            "  and hard to patch after a breach."
        ),
        context=(
            "Task: answer 'best practices for deploying LLMs in production' for an engineering "
            "team moving from prototype to production. Context: latency, cost, reliability, "
            "and prompt injection are the four main concerns. Structured, actionable output."
        ),
        notes=(
            "Addresses all four stated concerns explicitly. "
            "Concrete numbers (500ms, 20-40%, 30 days). "
            "Structured headers make it scannable."
        ),
    ),

    GeneralGoldenSample(
        sample_id="G-SR-002",
        agent_type="search",
        input_data={
            "search": "How should we structure our data team for a Series B startup?",
            "content": (
                "Context: 60-person startup, just raised Series B. Currently have 2 data analysts "
                "and 1 data engineer. CEO wants to hire 4 more data people in the next 6 months "
                "and is deciding between centralized vs. embedded team structure."
            ),
        },
        reference_output=(
            "DATA TEAM STRUCTURE — SERIES B RECOMMENDATION\n\n"
            "RECOMMENDATION: Centralized team with embedded rotations.\n\n"
            "WHY NOT FULLY EMBEDDED:\n"
            "At 60 people with 3 data people today, embedding now fragments an already thin "
            "team. You will end up with 5 people doing different things with no shared "
            "infrastructure, no common data quality standards, and no oncall coverage.\n\n"
            "WHY NOT FULLY CENTRALIZED (pure service model):\n"
            "Centralized teams at Series B tend to become ticket-taking operations that "
            "product teams route around after 6 months. Velocity dies.\n\n"
            "WHAT WORKS AT YOUR SIZE:\n"
            "- Hire a Head of Data first (not another IC). You need someone to own the roadmap "
            "  and make the hard prioritization calls.\n"
            "- Build a central platform team (2 data engineers) that owns the warehouse, "
            "  pipelines, and tooling.\n"
            "- Embed 1-2 analysts in your highest-revenue product area (growth or monetization) "
            "  on 6-month rotations — they stay on the central team's career ladder.\n"
            "- Re-evaluate at 150 people. By then product teams will be large enough to "
            "  support fully embedded data roles.\n\n"
            "SUGGESTED HIRE ORDER (next 4 hires):\n"
            "  1. Head of Data\n"
            "  2. Data Engineer (platform)\n"
            "  3. Analytics Engineer (dbt, data model ownership)\n"
            "  4. Analyst (embed in growth/monetization)"
        ),
        context=(
            "Task: advise a 60-person Series B startup on how to structure their data team. "
            "Currently 3 data people, hiring 4 more. Deciding between centralized vs embedded. "
            "Answer should give a concrete recommendation with reasoning and hire order."
        ),
        notes=(
            "Takes a clear position (centralized + embedded rotations). "
            "Explains why pure alternatives fail at this size. "
            "Hire order is the most concrete deliverable — leads with Head of Data."
        ),
    ),

    GeneralGoldenSample(
        sample_id="G-SR-003",
        agent_type="search",
        input_data={
            "search": "What is the difference between RAG and fine-tuning for LLMs?",
            "content": (
                "Context: product team is deciding whether to use RAG or fine-tuning to make "
                "an LLM answer questions about our internal product documentation. "
                "The documentation changes frequently (monthly updates)."
            ),
        },
        reference_output=(
            "RAG vs. FINE-TUNING — for frequently-updated internal documentation\n\n"
            "SHORT ANSWER: Use RAG. Fine-tuning is the wrong tool for this use case.\n\n"
            "WHY RAG:\n"
            "- Your documentation changes monthly. Fine-tuning bakes knowledge into model weights "
            "  — every update requires a new training run ($200–$2,000 depending on model size) "
            "  and a new deployment.\n"
            "- RAG decouples the knowledge store from the model: update the vector database, "
            "  done. No retraining, no deployment cycle.\n"
            "- RAG gives you citation: the model can return 'Source: Product FAQ v3, section 2.4.' "
            "  Fine-tuned models cannot reliably cite sources.\n\n"
            "WHEN FINE-TUNING IS BETTER:\n"
            "- Teaching the model a specific OUTPUT FORMAT it does not naturally produce "
            "  (e.g., always respond in JSON schema X).\n"
            "- Correcting systematic behavior patterns (tone, refusals) across all queries.\n"
            "- Static knowledge that will not change (legal jurisdiction rules, scientific constants).\n\n"
            "WHAT TO BUILD:\n"
            "  1. Chunk your docs into ~512-token segments, embed with text-embedding-3-small.\n"
            "  2. Store in a vector DB (Chroma/Pinecone/pgvector).\n"
            "  3. At query time: retrieve top-5 chunks, inject into system prompt, generate answer.\n"
            "  4. When docs update: re-embed changed files only (not the full corpus).\n\n"
            "Estimated build time: 2-3 engineer-days for a basic implementation."
        ),
        context=(
            "Task: explain RAG vs fine-tuning for a product team choosing an approach for "
            "LLM-powered internal documentation Q&A. Documentation changes monthly. "
            "Answer should give a clear recommendation, explain the tradeoffs, and "
            "describe what to actually build."
        ),
        notes=(
            "Takes a clear position upfront. "
            "Monthly updates constraint is used as the key decision factor. "
            "Fine-tuning use cases listed so the answer is complete, not one-sided. "
            "Build steps are concrete and time-estimated."
        ),
    ),
]


# ---------------------------------------------------------------------------
# thank_you  (G-TY-001 – G-TY-003)
# ---------------------------------------------------------------------------

_THANK_YOU_SAMPLES = [
    GeneralGoldenSample(
        sample_id="G-TY-001",
        agent_type="thank_you",
        input_data={
            "adjective": "technical",
            "position": "Staff Engineer",
            "content": (
                "Interview focused on system design (designed a distributed rate limiter). "
                "Interviewer was Elena Rodriguez, principal engineer. "
                "The conversation went deep on consistency tradeoffs in distributed systems."
            ),
        },
        reference_output=(
            "Subject: Thank you — Staff Engineer interview\n\n"
            "Hi Elena,\n\n"
            "Thank you for the thoughtful system design discussion today. "
            "The conversation about consistency tradeoffs in the rate limiter — "
            "specifically the tension between strict per-region enforcement and "
            "the latency cost of cross-region coordination — was the most "
            "substantive design discussion I have had in an interview in a while.\n\n"
            "It sharpened my thinking on a real problem I have faced: we chose "
            "eventual consistency with a 2-second synchronization window, and your "
            "question about what happens at window boundaries pushed me to think "
            "through an edge case I had glossed over. I would approach the boundary "
            "handling differently now.\n\n"
            "I remain genuinely excited about the role. Thanks again for your time.\n\n"
            "Best,\n[Candidate Name]"
        ),
        context=(
            "Task: write a technical thank you note after a Staff Engineer interview. "
            "Interviewer: Elena Rodriguez (principal engineer). Topic: distributed rate limiter "
            "system design, with deep discussion on consistency tradeoffs. "
            "Note should be specific to the conversation, not generic."
        ),
        notes=(
            "References the specific technical topic (rate limiter + consistency). "
            "Shows intellectual engagement by reflecting on something learned. "
            "No filler phrases like 'It was a pleasure to meet you.'"
        ),
    ),

    GeneralGoldenSample(
        sample_id="G-TY-002",
        agent_type="thank_you",
        input_data={
            "adjective": "warm",
            "position": "Product Manager",
            "content": (
                "Final round interview with the CPO, Marcus Chen. "
                "Discussed the company's 3-year product vision and where the PM would fit. "
                "CPO shared a candid challenge: the current roadmap is overloaded and the "
                "team needs someone who can make hard prioritization calls."
            ),
        },
        reference_output=(
            "Subject: Thank you — Product Manager conversation\n\n"
            "Hi Marcus,\n\n"
            "Thank you for the candid conversation today, and especially for sharing "
            "the real challenge: a roadmap that has grown faster than the team's capacity "
            "to execute it well. That kind of honesty made the conversation feel substantive "
            "rather than performative.\n\n"
            "What resonated with me most was your framing of the PM role as 'the person "
            "who says no clearly enough that the team can say yes to the right things.' "
            "That is exactly the kind of work I find most valuable — not the easy prioritization "
            "calls, but the ones where you have to push back on a stakeholder with real "
            "organizational standing.\n\n"
            "I am genuinely interested in the role, and I am confident I can help bring "
            "focus to the roadmap. I look forward to hearing from you.\n\n"
            "Best,\n[Candidate Name]"
        ),
        context=(
            "Task: write a warm thank you after a CPO-level final interview for a PM role. "
            "CPO shared a candid challenge (overloaded roadmap). Note should acknowledge "
            "the candor, reflect on something specific said, and reaffirm fit."
        ),
        notes=(
            "Quotes the CPO's framing ('says no clearly enough'). "
            "Acknowledges the candor directly — this signals listening. "
            "Closes with confidence, not desperation."
        ),
    ),

    GeneralGoldenSample(
        sample_id="G-TY-003",
        agent_type="thank_you",
        input_data={
            "adjective": "enthusiastic",
            "position": "Data Scientist",
            "content": (
                "Phone screen with recruiter, Sarah Park. "
                "20-minute call covering background, salary range, and timeline. "
                "Recruiter mentioned the team is expanding into NLP for customer support automation."
            ),
        },
        reference_output=(
            "Subject: Thank you — Data Scientist conversation\n\n"
            "Hi Sarah,\n\n"
            "Thank you for the call today. It was helpful to get a clear picture of the "
            "timeline and the team's direction.\n\n"
            "The NLP work for customer support automation is the part I am most excited about. "
            "I have spent the last two years building text classification and intent detection "
            "models for a similar use case, so the fit felt immediate when you described it.\n\n"
            "Looking forward to the next steps. Please let me know if you need anything "
            "from my side to move things along.\n\n"
            "Best,\n[Candidate Name]"
        ),
        context=(
            "Task: write an enthusiastic but brief thank you after a recruiter phone screen "
            "for a Data Scientist role. Recruiter: Sarah Park. Key detail: team is expanding "
            "into NLP for customer support automation. Note should be short, warm, and specific."
        ),
        notes=(
            "Appropriate length for a phone screen (not a final round). "
            "Connects candidate's experience to the NLP detail the recruiter mentioned. "
            "No filler, clean close."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_ALL_SAMPLES: list[GeneralGoldenSample] = (
    _COVER_LETTER_SAMPLES
    + _JOB_APPLICATION_SAMPLES
    + _JOB_INTERVIEW_SAMPLES
    + _KEYWORDS_EXTRACTION_SAMPLES
    + _MESSAGE_SAMPLES
    + _SEARCH_SAMPLES
    + _THANK_YOU_SAMPLES
)


def load_general_golden_samples(
    agent_type: str | None = None,
) -> list[GeneralGoldenSample]:
    """Return all general golden samples, optionally filtered by agent_type."""
    if agent_type:
        return [s for s in _ALL_SAMPLES if s.agent_type == agent_type]
    return list(_ALL_SAMPLES)


GENERAL_AGENT_TYPES: list[str] = [
    "cover_letter",
    "job_application",
    "job_interview",
    "keywords_extraction",
    "message",
    "search",
    "thank_you",
]
