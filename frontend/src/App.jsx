
import { useEffect, useState } from "react";
import "./App.css";

const API_URL = "http://127.0.0.1:5000";

const emptyProfile = {
  name: "",
  program: "MS Computer Science",
  year: "",
  bio: "",
  interests: "",
  skills: "",
  advice_topics: "",
  completed_courses: "",
  current_courses: "",
  willing_to_advise: true,
};

const emptyFilters = {
  program: "",
  year: "",
  skills: "",
  advice_topics: "",
  availableOnly: true,
};

const emptyConnectionRequest = {
  requester_name: "",
  requester_email: "",
  course_code: "",
  advice_topic: "",
  message: "",
};

function coursesToText(courses = []) {
  return Array.isArray(courses) ? courses.join(", ") : "";
}

function textToCourses(value) {
  return value
    .split(/[,\n]/)
    .map((courseCode) => courseCode.trim())
    .filter(Boolean);
}

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

function ConnectionRequestForm({ student, defaultCourse, onRequestCreated }) {
  const [requestForm, setRequestForm] = useState({
    ...emptyConnectionRequest,
    course_code: defaultCourse,
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  function updateRequestField(field, value) {
    setRequestForm((currentForm) => ({
      ...currentForm,
      [field]: value,
    }));
  }

  async function submitRequest(event) {
    event.preventDefault();
    if (submitting) return;

    setError("");
    setSuccess("");
    setSubmitting(true);

    try {
      const request = {
        id: crypto.randomUUID(),
        student_id: student.id,
        student_name: student.name,
        requester_name: requestForm.requester_name.trim(),
        requester_email: requestForm.requester_email.trim(),
        course_code: requestForm.course_code.trim().toUpperCase(),
        advice_topic: requestForm.advice_topic.trim(),
        message: requestForm.message.trim(),
        status: "pending",
        created_at: new Date().toISOString(),
      };

      setSuccess(`Request sent to ${student.name}.`);
      setRequestForm({
        ...emptyConnectionRequest,
        course_code: defaultCourse,
      });
      onRequestCreated(request);
    } catch (err) {
      setError(err.message || "Could not send the request.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="request-form" onSubmit={submitRequest}>
      <h4>Request advice from {student.name}</h4>
      <p className="profile-note">
        Send context first. Messaging should happen after the request is accepted.
      </p>

      <div className="request-grid">
        <label>
          Your name
          <input
            value={requestForm.requester_name}
            onChange={(event) =>
              updateRequestField("requester_name", event.target.value)
            }
            maxLength={100}
            required
            disabled={submitting}
          />
        </label>

        <label>
          Email
          <input
            type="email"
            value={requestForm.requester_email}
            onChange={(event) =>
              updateRequestField("requester_email", event.target.value)
            }
            maxLength={160}
            disabled={submitting}
          />
        </label>

        <label>
          Course
          <input
            value={requestForm.course_code}
            onChange={(event) =>
              updateRequestField("course_code", event.target.value)
            }
            placeholder="CSC 510"
            maxLength={30}
            required
            disabled={submitting}
          />
        </label>

        <label>
          Advice topic
          <input
            value={requestForm.advice_topic}
            onChange={(event) =>
              updateRequestField("advice_topic", event.target.value)
            }
            placeholder="Projects, workload, prep"
            maxLength={80}
            required
            disabled={submitting}
          />
        </label>

        <label className="wide-field">
          Message
          <textarea
            value={requestForm.message}
            onChange={(event) =>
              updateRequestField("message", event.target.value)
            }
            placeholder="Share what you want help with and why this student seems relevant."
            maxLength={1000}
            rows={4}
            required
            disabled={submitting}
          />
        </label>
      </div>

      {error && <p className="error-message" role="alert">{error}</p>}
      {success && <p className="message-success" role="status">{success}</p>}

      <button
        type="submit"
        disabled={
          submitting ||
          !requestForm.requester_name.trim() ||
          !requestForm.course_code.trim() ||
          !requestForm.advice_topic.trim() ||
          !requestForm.message.trim()
        }
      >
        {submitting ? "Sending..." : "Send Request"}
      </button>
    </form>
  );
}

function RequestReviewPanel({ requests, loading, onStatusChange, onRefresh }) {
  return (
    <section className="request-panel">
      <div className="section-heading">
        <div>
          <h3>Advice requests</h3>
          <p>Frontend-only prototype until requests belong to Supabase accounts.</p>
        </div>
        <button type="button" onClick={onRefresh}>
          Clear handled
        </button>
      </div>

      {loading ? (
        <p className="empty-state">Loading requests...</p>
      ) : requests.length === 0 ? (
        <p className="empty-state">No advice requests yet.</p>
      ) : (
        <div className="request-list">
          {requests.map((request) => (
            <article className="request-card" key={request.id}>
              <div>
                <div className="request-card-header">
                  <strong>{request.requester_name}</strong>
                  <span className={`status-badge ${request.status}`}>
                    {request.status}
                  </span>
                </div>
                <p>
                  wants advice from <strong>{request.student_name}</strong> for{" "}
                  <strong>{request.course_code}</strong>
                </p>
                <p>
                  <strong>Topic: </strong>
                  {request.advice_topic}
                </p>
                <p>{request.message}</p>
                {request.requester_email && (
                  <p className="profile-note">{request.requester_email}</p>
                )}
              </div>

              {request.status === "pending" && (
                <div className="request-actions">
                  <button
                    type="button"
                    onClick={() => onStatusChange(request.id, "accepted")}
                  >
                    Accept
                  </button>
                  <button
                    type="button"
                    onClick={() => onStatusChange(request.id, "declined")}
                  >
                    Decline
                  </button>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function App() {
  const [course, setCourse] = useState("CSC 510");
  const [filters, setFilters] = useState(emptyFilters);
  const [students, setStudents] = useState([]);
  const [selectedStudent, setSelectedStudent] = useState(null);
  const [profileForm, setProfileForm] = useState(emptyProfile);
  const [editingStudentId, setEditingStudentId] = useState(null);
  const [showProfileForm, setShowProfileForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [requests, setRequests] = useState([]);
  const [requestsLoading] = useState(false);
  const [profileSaving, setProfileSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  function searchUrl(searchCourse = course, searchFilters = filters) {
    const params = new URLSearchParams();

    if (searchCourse.trim()) params.set("course", searchCourse.trim());
    if (searchFilters.program.trim()) {
      params.set("program", searchFilters.program.trim());
    }
    if (searchFilters.year.trim()) params.set("year", searchFilters.year.trim());
    if (searchFilters.skills.trim()) {
      params.set("skills", searchFilters.skills.trim());
    }
    if (searchFilters.advice_topics.trim()) {
      params.set("advice_topics", searchFilters.advice_topics.trim());
    }
    params.set("available", String(searchFilters.availableOnly));

    return `${API_URL}/api/students/search?${params.toString()}`;
  }

  function hasSearchCriteria(searchCourse = course, searchFilters = filters) {
    return Boolean(
      searchCourse.trim() ||
        searchFilters.program.trim() ||
        searchFilters.year.trim() ||
        searchFilters.skills.trim() ||
        searchFilters.advice_topics.trim()
    );
  }

  async function searchStudents(
    searchCourse = course,
    searchFilters = filters
  ) {
    if (!hasSearchCriteria(searchCourse, searchFilters)) {
      setError("Please enter a course code or at least one filter.");
      setStudents([]);
      return;
    }

    setLoading(true);
    setError("");
    setNotice("");
    setSelectedStudent(null);

    try {
      const response = await fetch(searchUrl(searchCourse, searchFilters));

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
    setNotice("");

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

  function addConnectionRequest(request) {
    setRequests((currentRequests) => [request, ...currentRequests]);
  }

  function updateConnectionRequestStatus(requestId, status) {
    setError("");
    setNotice("");
    setRequests((currentRequests) =>
      currentRequests.map((request) =>
        request.id === requestId ? { ...request, status } : request
      )
    );
    setNotice(`Request ${status}.`);
  }

  function clearHandledRequests() {
    setRequests((currentRequests) =>
      currentRequests.filter((request) => request.status === "pending")
    );
  }

  function updateProfileField(field, value) {
    setProfileForm((currentProfile) => ({
      ...currentProfile,
      [field]: value,
    }));
  }

  function updateFilter(field, value) {
    setFilters((currentFilters) => ({
      ...currentFilters,
      [field]: value,
    }));
  }

  function resetFilters() {
    const resetState = { ...emptyFilters };
    setFilters(resetState);
    searchStudents(course, resetState);
  }

  function profileMatchesSearch(student, completedCourses) {
    const normalizedCourse = course.trim().toUpperCase();
    const hasCourseMatch =
      !normalizedCourse ||
      completedCourses
        .map((courseCode) => courseCode.toUpperCase())
        .includes(normalizedCourse);

    const containsFilter = (value, filterValue) =>
      !filterValue.trim() ||
      String(value || "")
        .toLowerCase()
        .includes(filterValue.trim().toLowerCase());

    return (
      hasCourseMatch &&
      (!filters.availableOnly || student.willing_to_advise) &&
      containsFilter(student.program, filters.program) &&
      containsFilter(student.year, filters.year) &&
      containsFilter(student.skills, filters.skills) &&
      containsFilter(student.advice_topics, filters.advice_topics)
    );
  }


  function startCreateProfile() {
    setEditingStudentId(null);
    setProfileForm({
      ...emptyProfile,
      completed_courses: course.trim(),
    });
    setShowProfileForm(true);
    setSelectedStudent(null);
    setError("");
    setNotice("");
  }

  function startEditProfile(student) {
    setEditingStudentId(student.id);
    setProfileForm({
      name: student.name || "",
      program: student.program || "",
      year: student.year || "",
      bio: student.bio || "",
      interests: student.interests || "",
      skills: student.skills || "",
      advice_topics: student.advice_topics || "",
      completed_courses: coursesToText(student.completed_courses),
      current_courses: coursesToText(student.current_courses),
      willing_to_advise: Boolean(student.willing_to_advise),
    });
    setShowProfileForm(true);
    setError("");
    setNotice("");
  }

  function closeProfileForm() {
    setShowProfileForm(false);
    setEditingStudentId(null);
    setProfileForm(emptyProfile);
  }

  async function saveProfile(event) {
    event.preventDefault();
    setProfileSaving(true);
    setError("");
    setNotice("");

    const payload = {
      ...profileForm,
      completed_courses: textToCourses(profileForm.completed_courses),
      current_courses: textToCourses(profileForm.current_courses),
    };

    try {
      const response = await fetch(
        editingStudentId
          ? `${API_URL}/api/students/${editingStudentId}`
          : `${API_URL}/api/students`,
        {
          method: editingStudentId ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      );
      const data = await response.json();

      if (!response.ok) throw new Error(data.error || "Unable to save profile.");

      setSelectedStudent(data.student);
      setShowProfileForm(false);
      setEditingStudentId(null);
      setProfileForm(emptyProfile);
      setNotice(editingStudentId ? "Profile updated." : "Profile created.");
      setStudents((currentStudents) => {
        if (!profileMatchesSearch(data.student, payload.completed_courses)) {
          return currentStudents.filter(
            (student) => student.id !== data.student.id
          );
        }

        const summary = {
          id: data.student.id,
          name: data.student.name,
          program: data.student.program,
          year: data.student.year,
        };

        if (currentStudents.some((student) => student.id === summary.id)) {
          return currentStudents.map((student) =>
            student.id === summary.id ? summary : student
          );
        }

        return [...currentStudents, summary].sort((first, second) =>
          first.name.localeCompare(second.name)
        );
      });
    } catch (err) {
      setError(err.message || "Could not save the student profile.");
    } finally {
      setProfileSaving(false);
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    async function loadStudents() {
      try {
        const response = await fetch(
          `${API_URL}/api/students/search?course=CSC%20510&available=true`,
          { signal: controller.signal }
        );
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

          <div className="filter-panel" aria-label="Search filters">
            <label>
              Program
              <input
                value={filters.program}
                onChange={(event) =>
                  updateFilter("program", event.target.value)
                }
                placeholder="MS Computer Science"
              />
            </label>

            <label>
              Year
              <input
                value={filters.year}
                onChange={(event) => updateFilter("year", event.target.value)}
                placeholder="Second Year"
              />
            </label>

            <label>
              Skills
              <input
                value={filters.skills}
                onChange={(event) =>
                  updateFilter("skills", event.target.value)
                }
                placeholder="React, Python"
              />
            </label>

            <label>
              Advice topics
              <input
                value={filters.advice_topics}
                onChange={(event) =>
                  updateFilter("advice_topics", event.target.value)
                }
                placeholder="Projects, Workload"
              />
            </label>

            <label className="filter-checkbox">
              <input
                type="checkbox"
                checked={filters.availableOnly}
                onChange={(event) =>
                  updateFilter("availableOnly", event.target.checked)
                }
              />
              Available only
            </label>

            <button type="button" onClick={resetFilters}>
              Reset
            </button>
          </div>

          <p className="search-hint">
            Try searching for CSC 510, CSC 540, or CSC 515.
          </p>

          <button
            className="secondary-action"
            type="button"
            onClick={startCreateProfile}
          >
            Create Student Profile
          </button>
        </section>

        {error && <div className="error-message">{error}</div>}
        {notice && <div className="success-message">{notice}</div>}

        <RequestReviewPanel
          requests={requests}
          loading={requestsLoading}
          onStatusChange={updateConnectionRequestStatus}
          onRefresh={clearHandledRequests}
        />

        {showProfileForm && (
          <section className="profile-editor">
            <div className="profile-heading">
              <div>
                <h3>
                  {editingStudentId
                    ? "Edit Student Profile"
                    : "Create Student Profile"}
                </h3>
                <p>
                  Add searchable academic and advice details for PackConnect.
                </p>
              </div>
              <button
                className="close-button"
                onClick={closeProfileForm}
                type="button"
                aria-label="Close profile editor"
              >
                ✕
              </button>
            </div>

            <form className="profile-form" onSubmit={saveProfile}>
              <label>
                Name
                <input
                  value={profileForm.name}
                  onChange={(event) =>
                    updateProfileField("name", event.target.value)
                  }
                  placeholder="Alex Morgan"
                  required
                />
              </label>

              <label>
                Program
                <input
                  value={profileForm.program}
                  onChange={(event) =>
                    updateProfileField("program", event.target.value)
                  }
                  placeholder="MS Computer Science"
                  required
                />
              </label>

              <label>
                Year
                <input
                  value={profileForm.year}
                  onChange={(event) =>
                    updateProfileField("year", event.target.value)
                  }
                  placeholder="Second Year"
                  required
                />
              </label>

              <label>
                Completed courses
                <input
                  value={profileForm.completed_courses}
                  onChange={(event) =>
                    updateProfileField(
                      "completed_courses",
                      event.target.value
                    )
                  }
                  placeholder="CSC 510, CSC 540"
                />
              </label>

              <label>
                Current courses
                <input
                  value={profileForm.current_courses}
                  onChange={(event) =>
                    updateProfileField(
                      "current_courses",
                      event.target.value
                    )
                  }
                  placeholder="CSC 515, CSC 522"
                />
              </label>

              <label>
                Interests
                <input
                  value={profileForm.interests}
                  onChange={(event) =>
                    updateProfileField("interests", event.target.value)
                  }
                  placeholder="Software Engineering, Databases"
                />
              </label>

              <label>
                Skills
                <input
                  value={profileForm.skills}
                  onChange={(event) =>
                    updateProfileField("skills", event.target.value)
                  }
                  placeholder="React, Python, SQL"
                />
              </label>

              <label>
                Advice topics
                <input
                  value={profileForm.advice_topics}
                  onChange={(event) =>
                    updateProfileField("advice_topics", event.target.value)
                  }
                  placeholder="Workload, Projects, Course Prep"
                />
              </label>

              <label className="wide-field">
                Bio
                <textarea
                  value={profileForm.bio}
                  onChange={(event) =>
                    updateProfileField("bio", event.target.value)
                  }
                  placeholder="Share what kind of course advice you can offer."
                  rows={4}
                />
              </label>

              <label className="checkbox-field wide-field">
                <input
                  type="checkbox"
                  checked={profileForm.willing_to_advise}
                  onChange={(event) =>
                    updateProfileField(
                      "willing_to_advise",
                      event.target.checked
                    )
                  }
                />
                Available to give advice
              </label>

              <div className="form-actions wide-field">
                <button type="button" onClick={closeProfileForm}>
                  Cancel
                </button>
                <button type="submit" disabled={profileSaving}>
                  {profileSaving ? "Saving..." : "Save Profile"}
                </button>
              </div>
            </form>
          </section>
        )}

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

                  {student.advice_topics && (
                    <p className="student-year">
                      Can help with {student.advice_topics}
                    </p>
                  )}

                  <span className="available-badge">
                    {student.willing_to_advise
                      ? "✓ Willing to share advice"
                      : "Not currently available"}
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

                {selectedStudent.completed_courses?.length > 0 && (
                  <div className="profile-tags">
                    <strong>Completed: </strong>
                    {selectedStudent.completed_courses.map((courseCode) => (
                      <span key={courseCode}>{courseCode}</span>
                    ))}
                  </div>
                )}

                {selectedStudent.current_courses?.length > 0 && (
                  <div className="profile-tags">
                    <strong>Current: </strong>
                    {selectedStudent.current_courses.map((courseCode) => (
                      <span key={courseCode}>{courseCode}</span>
                    ))}
                  </div>
                )}

                {selectedStudent.interests && (
                  <p className="profile-bio">
                    <strong>Interests: </strong>
                    {Array.isArray(selectedStudent.interests)
                      ? selectedStudent.interests.join(", ")
                      : selectedStudent.interests}
                  </p>
                )}

                {selectedStudent.skills && (
                  <p className="profile-bio">
                    <strong>Skills: </strong>
                    {selectedStudent.skills}
                  </p>
                )}

                {selectedStudent.advice_topics && (
                  <p className="profile-bio">
                    <strong>Can help with: </strong>
                    {selectedStudent.advice_topics}
                  </p>
                )}

                <button
                  className="profile-button"
                  type="button"
                  onClick={() => startEditProfile(selectedStudent)}
                >
                  Edit Profile
                </button>
              </div>
            </div>
            <ConnectionRequestForm
              key={`request-${selectedStudent.id}`}
              student={selectedStudent}
              defaultCourse={course}
              onRequestCreated={addConnectionRequest}
            />
            <MessageForm key={`message-${selectedStudent.id}`} student={selectedStudent} />
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
