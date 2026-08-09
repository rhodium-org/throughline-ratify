# Security Policy

`throughline-ratify` is a local terminal application that reads and writes files in
a project directory, and on a composed project resolves pinned sources over the
network. It has no server, no runtime authentication surface, and no credentials of
its own, so its attack surface is small — but reports are still welcome.

## Supported versions

throughline-ratify is pre-1.0 (alpha). Only the latest `main` is supported; fixes
land there.

## Reporting a vulnerability

Please report suspected vulnerabilities **privately**, not via a public issue:

- Use GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
  ("Report a vulnerability" under the repository's *Security* tab). Include details
  and, if possible, a minimal reproduction. The report reaches the maintainer
  (Henry Grech-Cini) privately.

Please give us a reasonable window to investigate and release a fix before any
public disclosure. We will acknowledge your report, keep you updated, and credit
you (if you wish) once a fix is available.

## Things worth reporting

The first one is this project's worst failure, and it is not obvious from outside:

- **Any route by which a ratification is recorded that a person did not take.**
  That includes a way to reach a ratify or reject decision without a human choosing
  it, a `--by` value that can be set to someone who did not sign off, or a
  ratification stamp written for content the reviewer was never shown. The
  accountability record is the one thing this whole toolchain exists to protect,
  and a false one is worse than none — see [`NG-0001`](idd/non-goals/NG-0001.yml).
- A crafted project file or requirements item that causes the cockpit to write
  outside the project directory, execute code, or crash unsafely.
- A way the cockpit reports a graph as sound when the underlying gate would reject
  it, or reports items as ratified when they are not. A false green in a review
  tool is a correctness *and* trust issue.
- A composed source that can be made to resolve to content other than the pinned
  ref, or to escape the local cache directory.
