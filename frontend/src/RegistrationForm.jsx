import { useState } from 'react'

export default function RegistrationForm({ apiUrl, onRegistered, onClose }) {
  const [values, setValues] = useState({
    name: '',
    email: '',
    password: '',
    confirmPassword: '',
    program: '',
    year: '',
    bio: '',
    interests: '',
    courses: '',
    willing: false,
  })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [registered, setRegistered] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmation, setShowConfirmation] = useState(false)

  function update(event) {
    const { name, value, checked, type } = event.target
    setValues((previous) => ({
      ...previous,
      [name]: type === 'checkbox' ? checked : value,
    }))
  }

  async function register(event) {
    event.preventDefault()
    if (submitting) return
    setError('')
    if (values.password !== values.confirmPassword) {
      setError('Passwords do not match.')
      return
    }
    setSubmitting(true)
    try {
      const response = await fetch(`${apiUrl}/api/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: values.name,
          email: values.email,
          password: values.password,
          program: values.program,
          year: values.year,
          bio: values.bio,
          interests: values.interests,
          willing_to_advise: values.willing,
          completed_courses: values.courses
            .split(',')
            .map((course) => course.trim())
            .filter(Boolean),
        }),
      })
      const data = await response.json()
      if (!response.ok)
        throw new Error(data.error || 'Unable to create your account.')
      setValues((previous) => ({
        ...previous,
        password: '',
        confirmPassword: '',
      }))
      setRegistered(true)
      onRegistered()
    } catch (err) {
      setError(
        err.message || 'Could not create your account. Please try again.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section
      className="registration-panel"
      id="registration"
      aria-labelledby="registration-title"
    >
      <div className="profile-heading">
        <h3 id="registration-title">Create your PackConnect account</h3>
        <button
          type="button"
          className="close-button"
          onClick={onClose}
          disabled={submitting}
          aria-label="Close registration"
        >
          ×
        </button>
      </div>
      {registered ? (
        <div role="status">
          <p className="message-success">
            Your account and student profile have been created.
          </p>
          <p>
            Sign in with your email and password to continue. If you opted in to
            advise, students can find you through your completed courses.
          </p>
          <button className="profile-button" onClick={onClose}>
            Back to sign in
          </button>
        </div>
      ) : (
        <form className="registration-form" onSubmit={register}>
          <p>
            Your name, program, year, bio, interests, and courses appear on your
            public student profile. Your email stays private.
          </p>
          <fieldset disabled={submitting}>
            <label htmlFor="register-name">Full name</label>
            <input
              id="register-name"
              name="name"
              value={values.name}
              onChange={update}
              autoComplete="name"
              maxLength={100}
              required
            />
            <label htmlFor="register-email">Email address</label>
            <input
              id="register-email"
              name="email"
              type="email"
              value={values.email}
              onChange={update}
              autoComplete="email"
              maxLength={254}
              required
            />
            <label htmlFor="register-password">Password</label>
            <div className="auth-password">
              <input
                id="register-password"
                name="password"
                type={showPassword ? 'text' : 'password'}
                value={values.password}
                onChange={update}
                autoComplete="new-password"
                minLength={12}
                maxLength={128}
                aria-describedby="password-help"
                required
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                aria-controls="register-password"
                aria-pressed={showPassword}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? 'Hide' : 'Show'}
              </button>
            </div>
            <span id="password-help" className="message-count">
              Use 12–128 characters.
            </span>
            <label htmlFor="register-confirm">Confirm password</label>
            <div className="auth-password">
              <input
                id="register-confirm"
                name="confirmPassword"
                type={showConfirmation ? 'text' : 'password'}
                value={values.confirmPassword}
                onChange={update}
                autoComplete="new-password"
                minLength={12}
                maxLength={128}
                required
              />
              <button
                type="button"
                onClick={() => setShowConfirmation(!showConfirmation)}
                aria-controls="register-confirm"
                aria-pressed={showConfirmation}
                aria-label={
                  showConfirmation
                    ? 'Hide confirmation password'
                    : 'Show confirmation password'
                }
              >
                {showConfirmation ? 'Hide' : 'Show'}
              </button>
            </div>
            <label htmlFor="register-program">Program</label>
            <input
              id="register-program"
              name="program"
              value={values.program}
              onChange={update}
              maxLength={100}
              placeholder="e.g. MS Computer Science"
              required
            />
            <label htmlFor="register-year">Year of study</label>
            <input
              id="register-year"
              name="year"
              value={values.year}
              onChange={update}
              maxLength={50}
              placeholder="e.g. First Year"
              required
            />
            <label htmlFor="register-bio">Bio (optional)</label>
            <textarea
              id="register-bio"
              name="bio"
              value={values.bio}
              onChange={update}
              maxLength={2000}
              rows={3}
            />
            <label htmlFor="register-interests">Interests (optional)</label>
            <input
              id="register-interests"
              name="interests"
              value={values.interests}
              onChange={update}
              maxLength={500}
            />
            <label htmlFor="register-courses">
              Completed courses (optional)
            </label>
            <input
              id="register-courses"
              name="courses"
              value={values.courses}
              onChange={update}
              maxLength={1600}
              placeholder="CSC 510, CSC 540"
              aria-describedby="courses-help"
            />
            <span id="courses-help" className="message-count">
              Separate course codes with commas. Up to 50 courses.
            </span>
            <label className="checkbox-label">
              <input
                type="checkbox"
                name="willing"
                checked={values.willing}
                onChange={update}
              />{' '}
              I’m willing to share advice with other students.
            </label>
            <p className="profile-note">
              Advisors start with five open advice slots. Change your limit or
              pause new requests from My profile after signing in.
            </p>
          </fieldset>
          {error && (
            <p className="error-message" role="alert">
              {error}
            </p>
          )}
          <button
            type="submit"
            className="register-submit"
            disabled={submitting}
          >
            {submitting ? 'Creating account...' : 'Create account'}
          </button>
        </form>
      )}
    </section>
  )
}
