- Can we have the bug report button go straight to a new github issue with
  the explorer name filled in? What about a bug report template? I could use
  guidance on what works best here.
- What happens if we upload two files with the same name, but different
  contents? Right now, they get separated by project ID (I think) but all
  files should only have one canonical source.  This seems like a larger fix
  is needed. If someone uploads something with the same name and it hashes to
  the same value, it should be a no-op, but the same name and a different hash
  value? This might be replacing older content, but it might be that it's
  genuinely different content. Is that correct?
- We need better ways of identifying sources. arXiv is good, but the others
  are not. We might need just filename. Or page or slide number. All text
  documents should use linenumber, and reuse code in code explorer.
- The downloaded filename should give an indication of what the conversation
  was about.
- We need a session history (that they can also delete individual sessions)
- When I issue a prompt, the response should include *which* documents in a
  topic have been consulted. If I return to a conversation later, the topic
  should only check those documents which were included in the *last* response
  from the LLM. Users can explicitly *choose* to include more documents in
  subsequent responses, but currently when I return to a topic, it checks
  *all* documents, so the user might accidentally pull in documents in the
  response that they were not expecting. 
- Voice mode?
- Audit: all endpoints should return correct status codes. We had one return a
  404 on duplicate topic id when it should have returned a 409:
- bottom bar for code/arxiv explorer needs size of data retrieved

oolong, choose scale:

| Scale | Questions | Characters | ~Tokens | Fill Ratio |
|-------|-----------|------------|---------|------------|
| 8K | 188 | 19K | 5.6K | 0.69 |
| 16K | 388 | 39K | 11.5K | 0.70 |
| 32K | 787 | 77K | 23K | 0.70 |
| 64K | 1,585 | 153K | 46K | 0.70 |
| 128K | 3,182 | 317K | 94K | 0.72 |
| 256K | 6,374 | 618K | 185K | 0.71 |
| 512K | 12,760 | 1.2M | 369K | 0.70 |
| 1M | 25,531 | 2.5M | 744K | 0.71 |

Fix schema:

    ❌ Bad Schema (Forces immediate guess):
    
    JSON
    {
      "final_answer": 42
    }
    ✅ Good Schema (Restores accuracy):
    
    JSON
    {
      "step_by_step_reasoning": "First, I calculated X... then I applied Y...",
      "final_answer": 42
    }

Logs on regex output (8k final result is 88%)


	2026-02-14 15:22:05,558 INFO     === OOLONG Benchmark Run ===
	2026-02-14 15:22:05,558 INFO     model=gpt-5-mini  run_base=True  run_rlm=False  max_windows=1
	2026-02-14 15:22:05,558 INFO     provider=openai  model=gpt-5-mini
	2026-02-14 15:22:05,558 INFO     modes=base  max_windows=1
	2026-02-14 15:22:05,558 INFO     Loading cached trec_coarse data...
	2026-02-14 15:22:05,968 INFO     Loaded from cache: /Users/poecurt/Library/CloudStorage/OneDrive-TheStarsGroup/Documents/ai/papers/projects/shesha/.worktrees/oolong-structured-output/oolong/trec_coarse.parquet (400 rows)
	2026-02-14 15:22:05,968 INFO     trec_coarse rows after length filter: 400
	2026-02-14 15:22:05,968 INFO     Context lengths present: [np.int64(8192), np.int64(16384), np.int64(32768), np.int64(65536), np.int64(131072), np.int64(262144), np.int64(524288), np.int64(1048576)]
	2026-02-14 15:22:05,969 INFO     Loaded 400 trec_coarse rows, 8 context lengths
	2026-02-14 15:22:06,027 INFO     Total steps: 360 (360 queries x 1 mode(s))
	2026-02-14 15:22:06,027 INFO     --- 8K window 1/1 (id=9, 25 oolong questions) ---
	2026-02-14 15:23:09,050 DEBUG    oolong base id=13000009 score=1.0 gold="['human being']" pred='{"answer": "Label: human being"}'
	2026-02-14 15:23:59,622 DEBUG    oolong base id=13000010 score=1.0 gold="['more common than']" pred='{"answer":"Answer: numeric value is more common than description and abstract concept"}'
	2026-02-14 15:25:07,676 DEBUG    oolong base id=13000011 score=1.0 gold="['more common than']" pred='{"answer":"Answer: numeric value is more common than human being"}'
	2026-02-14 15:26:09,012 DEBUG    oolong base id=13000012 score=1.0 gold="['less common than']" pred='{"answer":"Answer: numeric value is less common than location"}'
	2026-02-14 15:26:54,671 DEBUG    oolong base id=13000013 score=1.0 gold="['less common than']" pred='{"answer":"Answer: numeric value is less common than entity"}'
	2026-02-14 15:27:45,270 DEBUG    oolong base id=13000014 score=1.0 gold="['less common than']" pred='{"answer":"Answer: numeric value is less common than abbreviation"}'
	2026-02-14 15:28:38,004 DEBUG    oolong base id=13000015 score=1.0 gold="['less common than']" pred='{"answer":"Answer: description and abstract concept is less common than location"}'
	2026-02-14 15:29:23,105 DEBUG    oolong base id=13000016 score=1.0 gold="['less common than']" pred='{"answer":"Answer: description and abstract concept is less common than entity"}'
	2026-02-14 15:30:48,830 DEBUG    oolong base id=13000017 score=1.0 gold="['less common than']" pred='{"answer":"Answer: description and abstract concept is less common than abbreviation"}'
	2026-02-14 15:31:24,523 DEBUG    oolong base id=13000018 score=1.0 gold="['less common than']" pred='{"answer":"Answer: human being is less common than location"}'
	2026-02-14 15:32:13,075 DEBUG    oolong base id=13000019 score=1.0 gold="['less common than']" pred='{"answer": "Answer: human being is less common than entity"}'
	2026-02-14 15:32:53,666 DEBUG    oolong base id=13000020 score=1.0 gold="['less common than']" pred='{"answer": "Answer: human being is less common than abbreviation"}'
	2026-02-14 15:33:45,244 DEBUG    oolong base id=13000021 score=1.0 gold="['less common than']" pred='{"answer": "Answer: location is less common than entity"}'
	2026-02-14 15:34:56,815 DEBUG    oolong base id=13000022 score=1.0 gold="['less common than']" pred='{"answer": "Answer: location is less common than abbreviation"}'
	2026-02-14 15:35:51,119 DEBUG    oolong base id=13000023 score=0.8 gold='[28]' pred='{"answer": "Answer: 29"}'
	2026-02-14 15:36:40,260 DEBUG    oolong base id=13000024 score=0.3 gold='[23]' pred='{"answer": "Answer: 27"}'
	2026-02-14 15:37:29,275 DEBUG    oolong base id=13000025 score=0.6 gold='[20]' pred='{"answer": "Answer: 18"}'
	2026-02-14 15:38:04,507 DEBUG    oolong base id=13000026 score=0.3 gold='[35]' pred='{"answer": "Answer: 31"}'
	2026-02-14 15:39:09,003 DEBUG    oolong base id=13000027 score=0.8 gold='[40]' pred='{"answer": "Answer: 41"}'
	2026-02-14 15:40:11,787 DEBUG    oolong base id=13000028 score=0.4 gold='[42]' pred='{"answer": "39"}'
	2026-02-14 15:40:46,892 DEBUG    oolong base id=13000029 score=1.0 gold='[94706]' pred='{"answer": "User: 94706"}'
	2026-02-14 15:40:49,834 DEBUG    oolong base id=13000030 score=1.0 gold="['human being']" pred='{"answer": "Label: human being"}'
	2026-02-14 15:40:53,866 DEBUG    oolong base id=13000031 score=1.0 gold="['human being']" pred='{"answer": "Label: human being"}'
	2026-02-14 15:40:58,674 DEBUG    oolong base id=13000032 score=1.0 gold='[1]' pred='{"answer": "Answer: 1"}'
	2026-02-14 15:42:00,942 DEBUG    oolong base id=13000033 score=1.0 gold='[90816]' pred='{"answer": "User: 90816"}'
	2026-02-14 15:42:00,958 INFO     Labeled context: 188 entries, 56 users
	2026-02-14 15:44:46,461 DEBUG    pairs base t=1 f1=1.000 |pred|=496 |gold|=496
	2026-02-14 15:46:47,660 DEBUG    pairs base t=2 f1=0.967 |pred|=465 |gold|=435
	2026-02-14 15:48:25,116 DEBUG    pairs base t=3 f1=0.931 |pred|=406 |gold|=406
	2026-02-14 15:50:19,546 DEBUG    pairs base t=4 f1=0.855 |pred|=190 |gold|=210
	2026-02-14 15:52:47,241 DEBUG    pairs base t=5 f1=0.796 |pred|=91 |gold|=105
	2026-02-14 15:54:39,626 DEBUG    pairs base t=6 f1=0.953 |pred|=903 |gold|=903
	2026-02-14 15:57:51,428 DEBUG    pairs base t=7 f1=0.913 |pred|=253 |gold|=253
	2026-02-14 16:00:07,424 DEBUG    pairs base t=8 f1=0.918 |pred|=666 |gold|=630
	2026-02-14 16:03:03,707 DEBUG    pairs base t=9 f1=0.892 |pred|=351 |gold|=378
	2026-02-14 16:04:55,398 DEBUG    pairs base t=10 f1=0.811 |pred|=66 |gold|=45
	2026-02-14 16:11:41,799 DEBUG    pairs base t=11 f1=0.884 |pred|=145 |gold|=183
	2026-02-14 16:14:16,580 DEBUG    pairs base t=12 f1=1.000 |pred|=29 |gold|=29
	2026-02-14 16:14:31,049 INFO     
	Interrupted — saving partial results
	2026-02-14 16:14:31,060 INFO     Wrote /Users/poecurt/Library/CloudStorage/OneDrive-TheStarsGroup/Documents/ai/papers/projects/shesha/.worktrees/oolong-structured-output/oolong/oolong_results.csv (37 rows)
	2026-02-14 16:14:31,242 INFO     Wrote /Users/poecurt/Library/CloudStorage/OneDrive-TheStarsGroup/Documents/ai/papers/projects/shesha/.worktrees/oolong-structured-output/oolong/oolong_scaling.png
	2026-02-14 16:14:31,242 INFO     Done in 3146s  log: /Users/poecurt/Library/CloudStorage/OneDrive-TheStarsGroup/Documents/ai/papers/projects/shesha/.worktrees/oolong-structured-output/oolong/last-run.log
    
# TODO

- ChatArea and useAppState both register WebSocket handlers maintaining
  independent `phase` state, creating potential for state divergence between the
  thinking indicator and the status bar. (from code review S4)
- Shared ChatArea and ChatMessage render Markdown without
  `disallowedElements={['img']}`, unlike the arXiv wrapper which explicitly
  blocks images. LLM-generated `![](url)` syntax would render as `<img>` tags,
  enabling tracking pixels. (from code review S5)
- Need timing info on all traces!
- Deep research mode for longer context?

RLMs are known to scale up to 10M+ tokens, but OOLONG and OOLONG-Pairs drop.
This implies that large corpora will still produce suboptimal results. A new
strategy?

    - RLM takes prompt and does an initial scan to figure out what information
      it needs to analyze the prompt.
    - RLM then launches subagents whose sole job is to exame a *single*
      document and determine if it has relevant information and surface that.
    - Now grounded in the information and documents it needs, it then
      restarts.
    - Or we can try the CART

- Kill multi-repo experiment
- Save chat histories? !!!
- What about Named Entity Recognition? How do we pull this out? Named entities
  might be radically different for different contexts?
- When we select a topic, it deselects all papers. It should select all and
  then we can opt out.
- We now restrict analysis to only the information from the documents. That
  stops the "What is the Capital of Malawi?" problem. However, researchers
  might want:
    - general LLM knowlege
    - web searches
- Claude wasn't writing front-end tests, so we are skimpy there.
- Items in the web interface should have dialog tags/popups or whatever you
  call those short, decriptive tags that occur when you hover on them.
  CLAUDE.md should be updated to mention this for web interfaces. a11y is
  important, too.
- In collections, we should have a centralized spot for them, not in a
  particular topic and then copied to others. When deleting from a topic, it
  must NOT delete from the others.
- Web interface should always provide arXiv links to cited documents? Will we
  need custom prompts?
- Can we add a menu bar to the TUI?
- Web search?
- Read CLAUDE.md, AGENTS.md, or other files?
- Reorganize README to be better structured (include TOC?)
- Token cost estimator
- In TUI, "escape" in the output pane should immediately return you to the
  input pane (and scroll output pane to bottom?)
- Does the chat history need to be pruned, or show some kind of context limit
  for users so they can know when to clear it?
- Clarification? Should the LLM detect ambiguous commands and ask for
  clarification, offering various alternative explanations?
- scratch/shesha-architectural-flaws.md has possible architectural flaws

- Do we have cases where the generated Python passed to container fails to
  compile? If so, can we run a compile check (without running it) we pass to
  the container and regenerate? Will this make things more efficient? Will
  this create security holes?
- We need to double check that regex matches are non-destructive. Is the
  in-memory prompt read-only?

- Consider wrapping REPL output in `<repl_output type="untrusted_document_content">`
  tags in `format_code_echo()` (src/shesha/rlm/prompts.py). REPL output can
  contain verbatim document text printed by LLM-generated code, which is a
  prompt injection surface. The reference RLM also passes raw output, so this
  would be a Shesha-only hardening beyond the paper's design.
- Windows support? Paths may be an issue, but there may be more.
- Do we need to be able to run analysis on non-main branches? Very useful for PRs
- Need better name for repos in examples/repo.py
- Switch to allow deeper recursion level?
- Switch to allow docker container to allocate more memory?
- Users should be able to run `example/repo.py .` to automatically use the
  current directory. Errs out if it's not a git repo.

# Done

- Where is generated Python stored? (Is it stored?). Would be interesting to
  see and log.
- Extract all prompts and give users the chance to refine them.
- examples/repo.py needs some way of deleting repos
- LLM should be able to write final output to filesystem?
- Is there any need to cleanup generated artifacts? (nope)
- Verify prompts make it clear that the LLM will only use source documents to
  answer queries, not its own knowledge (prompts were not clear. This is now
  fixed)
- Verify the possible security restrictions we see in
  https://github.com/alexzhang13/rlm-minimal/blob/main/rlm/repl.py

/superpowers:brainstorm We have an RLM reference implementation at @rlm-minimal/rlm/repl.py. It looks like *maybe* it's trying to make sure that Python doesn't use any unsafe constructs when it's generating code for the RLM system. Is that correct? It sounds like a security feature we might want.
- Update README to highlight barsoom

I like the Claude code interface and the examples in `examples/*.py` should
use something similar. Layout would be like this:

 .--------------------------------------------------------------------.
 |  [output area]                                                     | 
 |                                                                    | 
 |                                                                    | 
 |                                                                    | 
 |                                                                    | 
 |                                                                    | 
 |                                                                    | 
 |                                                                    | 
 |                                                                    | 
 |                                                                    | 
 |                                                                    | 
 |                                                                    | 
 |                                                                    | 
 |--------------------------------------------------------------------| 
 | [info area]                                                        | 
 |--------------------------------------------------------------------| 
 | > [input area]                                                     | 
 .--------------------------------------------------------------------. 

The '| >     ' input area is where users type and text scrolls *above* that in
the output area. That input area can expand while users type. Shift-enter or a
trailing \ on a line lets the user enter multiple lines (or pasting text
works, but any pasted text longer than 3 lines should display as `[Pasted text
+9 lines]`. Hitting "enter" (without "shift") will send the

We have several built-in commands, such as "write", "help", and so on. From
now on all of those *must* being with a forward slash (/) (leading whitespace
ok), we should suggest some kind of auto-complete for allowed commands
accepting. Using a leading / for commands makes it easier for the user
separate commands from prompts.

We nee a new command, `markdown`, which allows the users to toggle terminal
markdown rendering on or off. This is used to nicely format the LLMs respons.
However, when using the `write` command, that must still output the raw
markdown, not a rendered version. However, I don't know how easy this is to
do.

We'd also like the lines around the input area and the info area to be
colorful, perhaps matching the blue from @images/shesha.png.

A user tapping escape twice should stop the thinking and allow the user to
enter a new prompt.

The [info area] should show what the LLM is now doing. We'd like a format
similar to the following:


 |--------------------------------------------------------------------------| 
 | Project: Ovid-Shesha | Tokens: 116763 (prompt: 110473, completion: 6290) |
 | Phase: [13.7s] [Iteration 3] Sub-LLM query                               |
 |--------------------------------------------------------------------------| 

The above should mean that we don't need to pass a --verbose flag any more.
the Phase should be the information take from the --verbose output while
running:

		[3.3s] [Iteration 1] Generating code
		[3.6s] [Iteration 1] Executing code
		[9.7s] [Iteration 2] Generating code
		[10.0s] [Iteration 2] Executing code
		[13.4s] [Iteration 3] Generating code
		[13.7s] [Iteration 3] Sub-LLM query
		[51.0s] [Iteration 3] Sub-LLM response
		[51.4s] [Iteration 3] Executing code
		[51.7s] [Iteration 3] Executing code
		[52.0s] [Iteration 3] Final answer
		[52.3s] [Iteration 3] verification


- Sometimes output is json instead of markdown. Need to correct that.
