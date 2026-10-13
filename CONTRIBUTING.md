# Contributing

Bug reports and pull requests are welcome.

## Reporting a bug

Press Send logs in 1401 (Windows) or the 1401 Mac app. It gives you a report ID like `NM-ABCD1234`. Open an issue
with that ID and describe what you see in a few sentences of your own.

## No AI-written contributions

Pull requests, issues and review comments must be written by a person who understands them. AI-written code,
descriptions and bug reports are closed without review.

## Pull requests

- One change per pull request, and say what you tested: your PC, the stick, what you ran and what it printed.
- Keep the description short: what was wrong, what you changed, how you tested it. Link the issue.
- Run the tests before you open it: `python3 -m unittest discover -s tests -t . -p 'test_*.py'`.
