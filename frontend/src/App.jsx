
import { useEffect, useState } from "react";
import "./App.css";
import { ConnectionRequestForm, RequestInbox, Conversation } from "./Messaging";
import { useRequests } from "./useRequests";

const API_URL = "";

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

function coursesToText(courses = []) {
  return Array.isArray(courses) ? courses.join(", ") : "";
}

function textToCourses(value) {
  return value
    .split(/[,\n]/)
    .map((courseCode) => courseCode.trim())
    .filter(Boolean);
}

function App({ user, onLogout, route, onUserUpdated }) {
  const isSearchPage = route === "app";
  const profileId = /^app\/students\/[1-9]\d*$/.test(route) ? Number(route.split("/")[2]) : ["app/profile", "app/profile/edit"].includes(route) ? user.id : null;
  const isEditing = route === "app/profile/edit";
  const [menuOpen, setMenuOpen] = useState(false);
  const [course, setCourse] = useState("CSC 510");
  const [filters, setFilters] = useState(emptyFilters);
  const [students, setStudents] = useState([]);
  const [selectedStudent, setSelectedStudent] = useState(null);
  const [profileError, setProfileError] = useState({ route: "", message: "" });
  const [profileForm, setProfileForm] = useState(emptyProfile);
  const [editingStudentId, setEditingStudentId] = useState(null);
  const [loading, setLoading] = useState(true);
  const { requests, loading: requestsLoading, error: requestsError, refresh: refreshRequests } = useRequests(route);
  const chatId = /^app\/chat\/[1-9]\d*$/.test(route) ? Number(route.split("/")[2]) : null;
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


  function startEditProfile(student) {
    setEditingStudentId(student.id);
    setProfileForm({
      name: student.name || "",
      program: student.program || "",
      year: student.year || "",
      bio: student.bio || "",
      interests: Array.isArray(student.interests)
        ? student.interests.join(", ")
        : student.interests || "",
      skills: student.skills || "",
      advice_topics: student.advice_topics || "",
      completed_courses: coursesToText(student.completed_courses),
      current_courses: coursesToText(student.current_courses),
      willing_to_advise: Boolean(student.willing_to_advise),
    });
    window.location.hash = "/app/profile/edit";
    setError("");
    setNotice("");
  }

  function closeProfileForm() {
    if (profileSaving) return;
    window.location.hash = "/app/profile";
    setEditingStudentId(null);
    setProfileForm(emptyProfile);
  }

  async function saveProfile(event) {
    event.preventDefault();
    if (profileSaving) return;
    if (!profileForm.name.trim()) {
      setError("Name is required.");
      return;
    }
    setProfileSaving(true);
    setError("");
    setNotice("");

    const payload = {
      ...Object.fromEntries(
        Object.entries(profileForm).map(([key, value]) => [
          key, typeof value === "string" ? value.trim() : value,
        ])
      ),
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
      window.location.hash = "/app/profile";
      setEditingStudentId(null);
      setProfileForm(emptyProfile);
      setNotice("Profile updated.");
      onUserUpdated(data.student);
      setStudents((currentStudents) => {
        if (!profileMatchesSearch(data.student, payload.completed_courses)) {
          return currentStudents.filter(
            (student) => student.id !== data.student.id
          );
        }

        const summary = data.student;

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

  useEffect(() => {
    if (!profileId) return;
    const controller = new AbortController();
    async function loadProfile() {
      try {
        const response = await fetch(`/api/students/${profileId}`, { signal: controller.signal });
        if (!response.ok) throw new Error(response.status === 404 ? "Student profile not found." : "Could not load this profile.");
        const { student } = await response.json();
        if (controller.signal.aborted) return;
        setSelectedStudent(student);
        setProfileError({ route, message: "" });
        setError("");
        setEditingStudentId(user.id);
        setProfileForm({
          ...student,
          interests: Array.isArray(student.interests) ? student.interests.join(", ") : student.interests || "",
          skills: student.skills || "", advice_topics: student.advice_topics || "",
          bio: student.bio || "",
          completed_courses: coursesToText(student.completed_courses),
          current_courses: coursesToText(student.current_courses),
          willing_to_advise: Boolean(student.willing_to_advise),
        });
      } catch (err) {
        if (!controller.signal.aborted) { setSelectedStudent(null); setProfileError({ route, message: err.message }); }
      }
    }
    loadProfile();
    return () => controller.abort();
  }, [profileId, user.id, route]);

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
          <div className="header-actions">
            <span className="university">NC State University</span>
            <span className="signed-in-name">{user.name}</span>
            <button className="profile-button" onClick={onLogout}>Sign out</button>
          </div>
        </div>
      </header>

      <nav className="workspace-nav" aria-label="Main navigation">
        <button className="menu-toggle" type="button" aria-expanded={menuOpen} aria-controls="workspace-links" onClick={() => setMenuOpen(!menuOpen)}>Menu</button>
        <div id="workspace-links" className={menuOpen ? "workspace-links open" : "workspace-links"} onClick={() => setMenuOpen(false)}>
          <a href="#/app" aria-current={isSearchPage ? "page" : undefined}>Find peers</a>
          <a href="#/app/requests" aria-current={route === "app/requests" ? "page" : undefined}>Requests {requests.length > 0 && <span>{requests.length}</span>}</a>
          <a href="#/app/profile" aria-current={route.startsWith("app/profile") ? "page" : undefined}>My profile</a>
          <a href="#/about">About</a>
        </div>
      </nav>
      <main className="main">
        {error && <div className="error-message" role="alert">{error}</div>}
        {notice && <div className="success-message" role="status">{notice}</div>}
        {isSearchPage && <section className="hero">
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

          <details className="advanced-filters"><summary>Advanced filters</summary>
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

          </details>
          <div className="filter-chips" aria-label="Active filters">
            {Object.entries(filters).filter(([key, value]) => key !== "availableOnly" && value.trim()).map(([key, value]) => <button key={key} type="button" onClick={() => { const next = { ...filters, [key]: "" }; setFilters(next); searchStudents(course, next); }}>{key.replaceAll("_", " ")}: {value} (remove)</button>)}
          </div>
          <p className="search-hint">
            Try searching for CSC 510, CSC 540, or CSC 515.
          </p>

        </section>}

        {route === "app/requests" && <RequestInbox user={user} requests={requests} loading={requestsLoading} error={requestsError} onRefresh={refreshRequests} />}
        {chatId && <Conversation key={chatId} requestId={chatId} user={user} />}

        {isEditing && selectedStudent?.id === user.id && (
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
                onClick={closeProfileForm} disabled={profileSaving}
                type="button"
                aria-label="Close profile editor"
              >
                ✕
              </button>
            </div>

            <form className="profile-form" onSubmit={saveProfile}>
              <fieldset className="profile-form-fields" disabled={profileSaving}>
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
                <button type="button" onClick={closeProfileForm} disabled={profileSaving}>
                  Cancel
                </button>
                <button type="submit" disabled={profileSaving}>
                  {profileSaving ? "Saving..." : "Save Profile"}
                </button>
              </div>
              </fieldset>
            </form>
          </section>
        )}

        {isSearchPage && <section className="results">
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

                  <a className="profile-button peer-profile-link" href={`#/app/students/${student.id}`}>
                    View Profile →
                  </a>
                </article>
              ))}
            </div>
          )}
        </section>}

        {profileError.route === route && profileError.message && <p className="error-message" role="alert">{profileError.message}</p>}
        {!isSearchPage && !profileId && !chatId && route !== "app/requests" && <div className="empty-state"><h2>Page not found</h2><a href="#/app">Back to Find peers</a></div>}
        {profileId && !(profileError.route === route && profileError.message) && selectedStudent?.id !== profileId && <p className="empty-state" role="status">Loading profile...</p>}
        {profileId && !isEditing && selectedStudent?.id === profileId && (
          <section className="profile-panel">
            <div className="profile-heading">
              <div><a className="profile-back" href="#/app">Back to peers</a><h2>{profileId === user.id ? "My profile" : "Student profile"}</h2></div>
              <button
                className="close-button"
                onClick={() => { window.location.hash = "/app"; }}
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

                {selectedStudent.id === user.id && <button
                  className="profile-button"
                  type="button"
                  onClick={() => startEditProfile(selectedStudent)}
                >
                  Edit Profile
                </button>}
              </div>
            </div>
            {selectedStudent.id !== user.id && (() => {
              const existing = requests.find((item) => item.sender_id === selectedStudent.id || item.recipient_id === selectedStudent.id);
              if (existing?.status === "accepted") return <p className="message-success">You're connected. <a className="chat-open" href={`#/app/chat/${existing.id}`}>Open chat</a></p>;
              if (existing?.status === "pending") return <p className="profile-note">A request is awaiting a response. <a href="#/app/requests">View requests</a></p>;
              if (!selectedStudent.can_receive_requests) return <p className="profile-note">This sample profile has no registered account to receive requests. Connect with a registered student instead.</p>;
              if (!selectedStudent.willing_to_advise) return <p className="profile-note">This student is not currently available for advice.</p>;
              return <ConnectionRequestForm key={selectedStudent.id} student={selectedStudent} defaultCourse={course} onRequestCreated={refreshRequests} />;
            })()}

          </section>
        )}
      </main>

      <footer className="footer">
        <nav className="app-legal-links" aria-label="Information"><a href="#/about">About</a><a href="#/privacy">Privacy policy</a><a href="#/terms">Terms &amp; conditions</a></nav>
        Peer Advice Portal · Software Engineering Project
      </footer>
    </div>
  );
}

export default App;
