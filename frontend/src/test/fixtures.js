export const student = {
  id: 1,
  name: 'Alex Morgan',
  program: 'MS Computer Science',
  year: 'Second Year',
  bio: 'Happy to help with projects.',
  interests: ['Databases'],
  skills: 'Python',
  advice_topics: 'Projects',
  completed_courses: ['CSC 510'],
  current_courses: [],
  willing_to_advise: true,
  can_receive_requests: true,
  accepting_requests: true,
  availability_status: 'available',
  max_open_requests: 5,
  pause_until: null,
  open_request_count: 0,
}
export const request = {
  id: 7,
  sender_id: 2,
  recipient_id: 1,
  sender_name: 'Sam Lee',
  recipient_name: student.name,
  course_code: 'CSC 510',
  advice_topic: 'Projects',
  message: 'How should I prepare?',
  status: 'pending',
  created_at: '2026-01-01T12:00:00Z',
}
export function response(data, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => data }
}
// Resolve explicitly to inspect the pending UI without sleeps or real latency.
export function deferred() {
  let resolve
  const promise = new Promise((done) => {
    resolve = done
  })
  return { promise, resolve }
}
