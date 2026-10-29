export function availabilityLabel(student) {
  const status = student.availability_status
  if (status === 'paused') {
    const date = new Date(
      `${student.pause_until}T00:00:00Z`,
    ).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      timeZone: 'UTC',
    })
    return `Paused until ${date} (Eastern time)`
  }
  if (status === 'at_capacity')
    return 'At capacity — not accepting new requests'
  if (status === 'unregistered') return 'No registered account'
  if (status === 'not_advising' || !student.willing_to_advise)
    return 'Not currently advising'
  return 'Accepting advice requests'
}

export function capacityLabel(student) {
  if (student.max_open_requests === null) return 'No request limit'
  return `${student.open_request_count ?? 0} of ${student.max_open_requests ?? 5} advice slots in use`
}
