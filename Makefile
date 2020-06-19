thesis.pdf: titlepage.pdf abstract.pdf \
            thesis.tex bibliography.bib \
	    evaluation.tex \
	    graphs/lobsters-memory.pdf \
	    graphs/lobsters-memlimit-cdf.pdf \
	    graphs/lobsters-pages-cdf.pdf \
	    graphs/vote-migration.pdf \
	    graphs/vote-migration-full.pdf \
	    graphs/vote-memlimit-cdf.pdf \
	    graphs/vote-throughput-memlimit.pdf \
	    graphs/vote-redis.pdf
	latexmk -pdf thesis.tex

proposal.pdf: 000-proposal.tex bibliography.bib \
              jfrg-thesis-proposal-agreement-robert.pdf \
              jfrg-thesis-proposal-agreement-frans.pdf \
              jfrg-thesis-proposal-agreement-sam.pdf \
              jfrg-thesis-proposal-agreement-malte.pdf \
              signature.pdf
	latexmk -pdf 000-proposal.tex
	cp 000-proposal.pdf $@

%.pdf: %.tex
	latexmk -pdf $<

graphs/source.pickle: graphs/ingest.py graphs/memoize.py \
                      $(wildcard benchmarks/orchestration/*.log) \
                      $(wildcard benchmarks/orchestration/*.hist) \
                      $(wildcard benchmarks/orchestration/*.json)
	graphs/memoize.py benchmarks/orchestration/ $@

graphs/vote-memlimit-cdf.pdf: graphs/source.pickle graphs/common.py graphs/vote-memlimit-cdf.py
	python graphs/vote-memlimit-cdf.py graphs/source.pickle benchmarks/orchestration/ graphs/vote-memlimit-cdf

graphs/lobsters-pages-cdf.pdf: graphs/source.pickle graphs/common.py graphs/lobsters-pages-cdf.py
	python graphs/lobsters-pages-cdf.py graphs/source.pickle benchmarks/orchestration/ graphs/lobsters-pages-cdf

graphs/lobsters-memlimit-cdf.pdf: graphs/source.pickle graphs/common.py graphs/lobsters-memlimit-cdf.py
	python graphs/lobsters-memlimit-cdf.py graphs/source.pickle benchmarks/orchestration/ graphs/lobsters-memlimit-cdf

graphs/%.pdf: graphs/source.pickle graphs/common.py graphs/%.py
	python graphs/$*.py graphs/source.pickle graphs/$*
