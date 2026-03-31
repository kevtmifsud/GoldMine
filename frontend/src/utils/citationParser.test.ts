import { describe, it, expect } from "vitest";
import {
  parseSingleCitation,
  citationToRoute,
  CITATION_REGEX,
} from "./citationParser";

describe("parseSingleCitation", () => {
  // Transcript citations
  it("parses earnings transcript", () => {
    const c = parseSingleCitation(
      "[AAPL | Earnings Transcript | Q4 2025 | CFO Remarks]"
    );
    expect(c).not.toBeNull();
    expect(c?.citationType).toBe("transcript");
    expect(c?.ticker).toBe("AAPL");
    expect(c?.docType).toBe("Earnings Transcript");
    expect(c?.period).toBe("Q4 2025");
    expect(c?.section).toBe("CFO Remarks");
  });

  // Estimate citations
  it("parses consensus estimate", () => {
    const c = parseSingleCitation(
      "[AAPL | Consensus | 2026A | as of 2026-03-21]"
    );
    expect(c).not.toBeNull();
    expect(c?.citationType).toBe("estimate");
    expect(c?.source).toBe("consensus");
    expect(c?.estimatePeriod).toBe("2026A");
    expect(c?.asOfDate).toBe("as of 2026-03-21");
    expect(c?.firm).toBeNull();
  });

  it("parses sellside estimate", () => {
    const c = parseSingleCitation(
      "[AAPL | Goldman Sachs | Alex Rivera | 2026A]"
    );
    expect(c).not.toBeNull();
    expect(c?.citationType).toBe("estimate");
    expect(c?.source).toBe("sellside");
    expect(c?.firm).toBe("Goldman Sachs");
    expect(c?.analystName).toBe("Alex Rivera");
    expect(c?.estimatePeriod).toBe("2026A");
  });

  it("parses buyside estimate", () => {
    const c = parseSingleCitation(
      "[AAPL | Tiger Global | James Wei | 2026A]"
    );
    expect(c).not.toBeNull();
    expect(c?.citationType).toBe("estimate");
    expect(c?.source).toBe("buyside");
    expect(c?.firm).toBe("Tiger Global");
    expect(c?.analystName).toBe("James Wei");
    expect(c?.estimatePeriod).toBe("2026A");
  });

  it("parses internal estimate", () => {
    const c = parseSingleCitation(
      "[AAPL | Internal | Alice Chen | 2026A]"
    );
    expect(c).not.toBeNull();
    expect(c?.citationType).toBe("estimate");
    expect(c?.source).toBe("internal");
    expect(c?.analystName).toBe("Alice Chen");
    expect(c?.estimatePeriod).toBe("2026A");
    expect(c?.firm).toBeNull();
  });

  // 3-segment citations
  it("parses 3-segment financial citation", () => {
    const c = parseSingleCitation("[AAPL | Financials | Q4 2024]");
    expect(c).not.toBeNull();
    expect(c?.citationType).toBe("financial");
    expect(c?.ticker).toBe("AAPL");
    expect(c?.period).toBe("Q4 2024");
  });

  // Special tickers
  it("parses BRK.B ticker", () => {
    const c = parseSingleCitation(
      "[BRK.B | Consensus | 2026A | as of 2026-03-21]"
    );
    expect(c).not.toBeNull();
    expect(c?.ticker).toBe("BRK.B");
    expect(c?.citationType).toBe("estimate");
  });

  it("parses BF.B ticker", () => {
    const c = parseSingleCitation(
      "[BF.B | Goldman Sachs | Alex Rivera | 2026A]"
    );
    expect(c).not.toBeNull();
    expect(c?.ticker).toBe("BF.B");
    expect(c?.citationType).toBe("estimate");
  });

  // Filing citations
  it("parses 10-K filing", () => {
    const c = parseSingleCitation(
      "[AAPL | 10-K | FY2024 | Risk Factors]"
    );
    expect(c).not.toBeNull();
    expect(c?.citationType).toBe("filing");
  });

  // Alt data
  it("parses alt data citation", () => {
    const c = parseSingleCitation(
      "[AAPL | Alt Data | credit_card | Q4 2024]"
    );
    expect(c).not.toBeNull();
    expect(c?.citationType).toBe("alt_data");
  });

  // Non-matching
  it("returns null for invalid text", () => {
    expect(parseSingleCitation("not a citation")).toBeNull();
  });
});

describe("citationToRoute", () => {
  it("routes estimates to estimates", () => {
    const c = parseSingleCitation(
      "[AAPL | Consensus | 2026A | as of 2026-03-21]"
    );
    expect(citationToRoute(c!)).toBe("estimates");
  });

  it("routes transcripts to transcripts", () => {
    const c = parseSingleCitation(
      "[AAPL | Earnings Transcript | Q4 2025 | CFO Remarks]"
    );
    expect(citationToRoute(c!)).toBe("transcripts");
  });

  it("never routes estimates to transcripts", () => {
    const c = parseSingleCitation(
      "[AAPL | Goldman Sachs | Alex Rivera | 2026A]"
    );
    expect(citationToRoute(c!)).not.toBe("transcripts");
    expect(citationToRoute(c!)).toBe("estimates");
  });

  it("routes filings to filings", () => {
    const c = parseSingleCitation(
      "[AAPL | 10-K | FY2024 | Risk Factors]"
    );
    expect(citationToRoute(c!)).toBe("filings");
  });
});

describe("CITATION_REGEX", () => {
  it("matches 4-segment citation", () => {
    const m = "[AAPL | Earnings Transcript | Q4 2025 | CFO]".match(CITATION_REGEX);
    expect(m).not.toBeNull();
    expect(m![4]).toBe("CFO");
  });

  it("matches 3-segment citation", () => {
    const m = "[AAPL | Financials | Q4 2024]".match(CITATION_REGEX);
    expect(m).not.toBeNull();
    expect(m![3]).toBe("Q4 2024");
    expect(m![4]).toBeUndefined();
  });

  it("matches dotted tickers", () => {
    const m = "[BRK.B | Financials | Q4 2024]".match(CITATION_REGEX);
    expect(m).not.toBeNull();
    expect(m![1]).toBe("BRK.B");
  });
});
