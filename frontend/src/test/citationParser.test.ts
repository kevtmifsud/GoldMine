import {
  parseSingleCitation,
  documentTypeToRoute,
  isFinancialData,
  parseFiscalPeriod,
} from "../utils/citationParser";

describe("parseSingleCitation", () => {
  it("parses a valid 4-part citation", () => {
    const result = parseSingleCitation(
      "[AAPL | Earnings Transcript | Q1 2026 | CFO Remarks]"
    );
    expect(result).toEqual({
      raw: "[AAPL | Earnings Transcript | Q1 2026 | CFO Remarks]",
      ticker: "AAPL",
      docType: "Earnings Transcript",
      period: "Q1 2026",
      section: "CFO Remarks",
    });
  });

  it("returns null for non-citation text", () => {
    expect(parseSingleCitation("just some text")).toBeNull();
  });

  it("trims whitespace around parts", () => {
    const result = parseSingleCitation(
      "[MSFT |  SEC Filing  |  Q3 2025  |  Risk Factors  ]"
    );
    expect(result).not.toBeNull();
    expect(result!.ticker).toBe("MSFT");
    expect(result!.docType).toBe("SEC Filing");
    expect(result!.period).toBe("Q3 2025");
    expect(result!.section).toBe("Risk Factors");
  });

  it("rejects tickers longer than 5 characters", () => {
    expect(
      parseSingleCitation("[TOOLONG | Type | Q1 2025 | Section]")
    ).toBeNull();
  });
});

describe("documentTypeToRoute", () => {
  it("maps known doc types to routes", () => {
    expect(documentTypeToRoute("Earnings Transcript")).toBe("transcripts");
    expect(documentTypeToRoute("SEC Filing")).toBe("filings");
    expect(documentTypeToRoute("Report")).toBe("sellside");
    expect(documentTypeToRoute("Notes")).toBe("notes");
    expect(documentTypeToRoute("Data Export")).toBe("data-files");
  });

  it("defaults to transcripts for unknown types", () => {
    expect(documentTypeToRoute("Unknown Type")).toBe("transcripts");
  });

  it("handles underscores in doc types", () => {
    expect(documentTypeToRoute("Earnings_Transcript")).toBe("transcripts");
  });
});

describe("isFinancialData", () => {
  it("returns true for financial doc types", () => {
    expect(isFinancialData("10-Q Filing")).toBe(true);
    expect(isFinancialData("10-K Filing")).toBe(true);
    expect(isFinancialData("Income Statement")).toBe(true);
    expect(isFinancialData("Balance Sheet")).toBe(true);
    expect(isFinancialData("Cash Flow")).toBe(true);
  });

  it("returns false for non-financial types", () => {
    expect(isFinancialData("Earnings Transcript")).toBe(false);
    expect(isFinancialData("Notes")).toBe(false);
  });
});

describe("parseFiscalPeriod", () => {
  it("parses Q1 2026 format", () => {
    expect(parseFiscalPeriod("Q1 2026")).toEqual({ quarter: 1, year: 2026 });
  });

  it("parses Q4_2025 format with underscore", () => {
    expect(parseFiscalPeriod("Q4_2025")).toEqual({ quarter: 4, year: 2025 });
  });

  it("is case-insensitive", () => {
    expect(parseFiscalPeriod("q2 2024")).toEqual({ quarter: 2, year: 2024 });
  });

  it("returns null for invalid periods", () => {
    expect(parseFiscalPeriod("2025")).toBeNull();
    expect(parseFiscalPeriod("FY2025")).toBeNull();
  });
});
