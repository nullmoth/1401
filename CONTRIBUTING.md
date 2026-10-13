# Contributing

Bug reports and pull requests are welcome.

## Reporting a bug

Press Send logs in 1401 (Windows) or the 1401 Mac app. It gives you a report ID like `NM-ABCD1234`. Open an issue
with that ID and describe what you see in a few sentences of your own.

## No AI-written contributions

Pull requests, issues and review comments must be written by a person who understands them. Code, descriptions or
bug reports written by an AI tool are closed without review.

- The pull request template has a box saying you wrote the change yourself. A pull request without it ticked fails
  the contribution check and is not reviewed.
- A pull request whose description or commits carry an AI tool's signature (its "generated with" footer or its
  co-author line) is closed automatically.
- Repeated AI-written submissions get the account blocked from the repository.

## Pull requests

- One change per pull request, and say what you tested: your PC, the stick, what you ran and what it printed.
- Keep the description short: what was wrong, what you changed, how you tested it. Link the issue.
- Run the tests before you open it: `python3 -m unittest discover -s tests -t . -p 'test_*.py'`.
