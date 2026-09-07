import { useState, type FormEvent } from "react";

interface AskEarthFormProps {
  onSubmit: (question: string) => void;
  disabled: boolean;
}

const RECENT_QUERIES_KEY = "ai-earth:recent-queries";
const MAX_RECENT_QUERIES = 8;

/** Reading/writing localStorage can throw (private browsing, blocked
 * site data, ...); recent queries are a convenience, never something the
 * page depends on to function. */
function readRecentQueries(): string[] {
  try {
    const raw = window.localStorage.getItem(RECENT_QUERIES_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((entry) => typeof entry === "string") : [];
  } catch {
    return [];
  }
}

function rememberQuery(question: string) {
  try {
    const deduped = [question, ...readRecentQueries().filter((entry) => entry !== question)];
    window.localStorage.setItem(
      RECENT_QUERIES_KEY,
      JSON.stringify(deduped.slice(0, MAX_RECENT_QUERIES)),
    );
  } catch {
    // per-browser convenience only; nothing else depends on this succeeding.
  }
}

export function AskEarthForm({ onSubmit, disabled }: AskEarthFormProps) {
  const [question, setQuestion] = useState("");
  const [recentQueries, setRecentQueries] = useState<string[]>(() => readRecentQueries());

  function handleSubmit(event: FormEvent) {
    event.preventDefault();

    const trimmed = question.trim();
    if (!trimmed) {
      return;
    }

    rememberQuery(trimmed);
    setRecentQueries(readRecentQueries());
    onSubmit(trimmed);
  }

  return (
    <div>
      <form onSubmit={handleSubmit}>
        <label htmlFor="ask-earth-question">Ask Earth a question</label>
        <textarea
          id="ask-earth-question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="e.g. How many wildfires occurred in Northern California last week?"
          rows={3}
          required
        />
        <button type="submit" disabled={disabled}>
          {disabled ? "Asking Earth..." : "Ask"}
        </button>
      </form>

      {recentQueries.length > 0 && (
        <div aria-label="Recent queries">
          <h2>Recent queries</h2>
          <ul>
            {recentQueries.map((recent) => (
              <li key={recent}>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => setQuestion(recent)}
                >
                  {recent}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
