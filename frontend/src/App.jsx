
import { useEffect, useState } from "react";
import "./App.css";

const API_URL = "http://127.0.0.1:5000";

function MessageForm({ student }) {
  const [senderName, setSenderName] = useState("");
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function sendMessage(event) {
    event.preventDefault();
    if (sending) return;
    setError("");
    setSuccess("");
    if (!senderName.trim() || !body.trim()) {
      setError("Please enter your name and a message.");
      return;
    }
    setSending(true);
    try {
      const response = await fetch(`${API_URL}/api/students/${student.id}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sender_name: senderName.trim(), body: body.trim() }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Unable to send message.");
      setBody("");
      setSuccess(`Message to ${student.name} saved successfully.`);
    } catch (err) {
      setError(err.message || "Could not send your message. Please try again.");
    } finally {
      setSending(false);
    }
  }

  return (
    <form className="message-form" onSubmit={sendMessage}>
      <h4>Send a message to {student.name}</h4>
      <p className="profile-note">Prototype: messages are saved locally. Student inboxes are not available yet.</p>
      <label htmlFor="sender-name">Your name</label>
      <input id="sender-name" value={senderName} onChange={(event) => { setSenderName(event.target.value); setSuccess(""); }} maxLength={100} required disabled={sending} autoComplete="name" />
      <label htmlFor="message-body">Message</label>
      <textarea id="message-body" value={body} onChange={(event) => { setBody(event.target.value); setSuccess(""); }} maxLength={2000} required disabled={sending} rows={5} placeholder="Ask about coursework, study tips, or their experience..." aria-describedby="message-count" />
      <span id="message-count" className="message-count">{body.length}/2000 characters</span>
      {error && <p className="error-message" role="alert">{error}</p>}
      {success && <p className="message-success" role="status">{success}</p>}
      <button type="submit" disabled={sending || !senderName.trim() || !body.trim()}>{sending ? "Sending..." : "Send Message"}</button>
    </form>
  );
}

function App() {
  const [course, setCourse] = useState("CSC 510");
  const [students, setStudents] = useState([]);
  const [selectedStudent, setSelectedStudent] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function searchStudents(searchCourse = course) {
    if (!searchCourse.trim()) {
      setError("Please enter a course code.");
      setStudents([]);
      return;
    }

    setLoading(true);
    setError("");
    setSelectedStudent(null);

    try {
      const response = await fetch(
        `${API_URL}/api/students/search?course=${encodeURIComponent(
          searchCourse.trim()
        )}`
      );

      if (!response.ok) {
        throw new Error("Unable to search students.");
      }

      const data = await response.json();
      setStudents(Array.isArray(data) ? data : data.students ?? []);
    } catch {
      setError(
        "Could not connect to the Flask backend. Make sure it is running on port 5000."
      );
      setStudents([]);
    } finally {
      setLoading(false);
    }
  }

  async function viewProfile(studentId) {
    setError("");

    try {
      const response = await fetch(
        `${API_URL}/api/students/${studentId}`
      );

      if (!response.ok) {
        throw new Error("Unable to load profile.");
      }

      const data = await response.json();
      setSelectedStudent(data.student ?? data);
    } catch {
      setError("Could not load the student's profile.");
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    async function loadStudents() {
      try {
        const response = await fetch(`${API_URL}/api/students/search?course=CSC%20510`, { signal: controller.signal });
        if (!response.ok) throw new Error("Unable to search students.");
        const data = await response.json();
        if (!controller.signal.aborted) setStudents(Array.isArray(data) ? data : data.students ?? []);
      } catch {
        if (!controller.signal.aborted) setError("Could not connect to the Flask backend. Make sure it is running on port 5000.");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    loadStudents();
    return () => controller.abort();
  }, []);

  return (
    <div className="app">
      <header className="header">
        <div className="header-content">
          <div className="brand">
            <span className="brand-icon">🎓</span>
            <div>
              <h1>PackConnect</h1>
              <p>Learn from students who've been there.</p>
            </div>
          </div>
          <span className="university">NC State University</span>
        </div>
      </header>

      <main className="main">
        <section className="hero">
          <span className="eyebrow">STUDENT-TO-STUDENT SUPPORT</span>
          <h2>Find someone who's taken your course.</h2>
          <p>
            Search by course code to discover students who have completed
            the course and volunteered to share their experience.
          </p>

          <form
            className="search-form"
            onSubmit={(event) => {
              event.preventDefault();
              searchStudents();
            }}
          >
            <input
              type="text"
              value={course}
              onChange={(event) => setCourse(event.target.value)}
              placeholder="Enter a course code, e.g. CSC 510"
              aria-label="Course code"
            />
            <button type="submit" disabled={loading}>
              {loading ? "Searching..." : "Find Students"}
            </button>
          </form>

          <p className="search-hint">
            Try searching for CSC 510, CSC 540, or CSC 515.
          </p>
        </section>

        {error && <div className="error-message">{error}</div>}

        <section className="results">
          <div className="section-heading">
            <div>
              <h3>Students who can help</h3>
              <p>
                Connect with peers who have experience in your course.
              </p>
            </div>
            <span className="result-count">
              {students.length} student{students.length !== 1 ? "s" : ""}
            </span>
          </div>

          {loading ? (
            <p className="empty-state">Searching for students...</p>
          ) : students.length === 0 ? (
            <p className="empty-state">
              No students found. Try another course code.
            </p>
          ) : (
            <div className="student-grid">
              {students.map((student) => (
                <article className="student-card" key={student.id}>
                  <div className="avatar">
                    {student.name
                      ?.split(" ")
                      .map((part) => part[0])
                      .slice(0, 2)
                      .join("")}
                  </div>

                  <h4>{student.name}</h4>

                  <p className="student-program">
                    {student.program || "NC State Student"}
                  </p>

                  {student.year && (
                    <p className="student-year">{student.year}</p>
                  )}

                  <span className="available-badge">
                    ✓ Willing to share advice
                  </span>

                  <button
                    className="profile-button"
                    onClick={() => viewProfile(student.id)}
                  >
                    View Profile →
                  </button>
                </article>
              ))}
            </div>
          )}
        </section>

        {selectedStudent && (
          <section className="profile-panel">
            <div className="profile-heading">
              <h3>Student Profile</h3>
              <button
                className="close-button"
                onClick={() => setSelectedStudent(null)}
                aria-label="Close profile"
              >
                ✕
              </button>
            </div>

            <div className="profile-content">
              <div className="avatar large-avatar">
                {selectedStudent.name
                  ?.split(" ")
                  .map((part) => part[0])
                  .slice(0, 2)
                  .join("")}
              </div>

              <div>
                <h4>{selectedStudent.name}</h4>
                <p>
                  {selectedStudent.program || "NC State Student"}
                  {selectedStudent.year
                    ? ` · ${selectedStudent.year}`
                    : ""}
                </p>

                {selectedStudent.bio && (
                  <p className="profile-bio">{selectedStudent.bio}</p>
                )}

                {selectedStudent.interests && (
                  <p className="profile-bio">
                    <strong>Interests: </strong>
                    {Array.isArray(selectedStudent.interests)
                      ? selectedStudent.interests.join(", ")
                      : selectedStudent.interests}
                  </p>
                )}

              </div>
            </div>
            <MessageForm key={selectedStudent.id} student={selectedStudent} />
          </section>
        )}
      </main>

      <footer className="footer">
        Peer Advice Portal · Software Engineering Project
      </footer>
    </div>
  );
}

export default App;
