// Small wrapper around fetch() for talking to the backend. Nginx proxies
// /api/* to the backend (see nginx/nginx.conf), so a plain relative path
// works both in the Docker deployment and if you ever add a dev proxy.
const API_BASE = '/api'

async function apiFetch(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    // Send/receive the session cookie.
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })

  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed (${response.status})`)
  }
  if (response.status === 204) {
    return null
  }
  return response.json()
}

export const login = (username, password) =>
  apiFetch('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) })

export const logout = () => apiFetch('/auth/logout', { method: 'POST' })

export const fetchCurrentUser = () => apiFetch('/auth/me')

export const requestPasswordReset = (email) =>
  apiFetch('/auth/password-reset/request', { method: 'POST', body: JSON.stringify({ email }) })

export const confirmPasswordReset = (token, newPassword) =>
  apiFetch('/auth/password-reset/confirm', {
    method: 'POST',
    body: JSON.stringify({ token, new_password: newPassword }),
  })

export const listUsers = () => apiFetch('/admin/users')

export const listProjects = () => apiFetch('/projects')

export const createProject = (projectName) =>
  apiFetch('/projects', { method: 'POST', body: JSON.stringify({ project_name: projectName }) })

export const listCommodities = (projectId) => apiFetch(`/projects/${projectId}/commodities`)

export const createCommodity = (projectId, name, code) =>
  apiFetch(`/projects/${projectId}/commodities`, {
    method: 'POST',
    body: JSON.stringify({ name, code }),
  })

export const listAnalyses = (commodityId) => apiFetch(`/commodities/${commodityId}/analyses`)

export const createAnalysis = (commodityId) =>
  apiFetch(`/commodities/${commodityId}/analyses`, { method: 'POST' })

export const getAnalysis = (analysisId) => apiFetch(`/analyses/${analysisId}`)

export const createGapEntry = (analysisId, entry) =>
  apiFetch(`/analyses/${analysisId}/gap`, { method: 'POST', body: JSON.stringify(entry) })

export const createFlushEntry = (analysisId, entry) =>
  apiFetch(`/analyses/${analysisId}/flush`, { method: 'POST', body: JSON.stringify(entry) })

export const listProcessTypes = () => apiFetch('/process-types')

export const createProcessType = (name) =>
  apiFetch('/process-types', { method: 'POST', body: JSON.stringify({ name }) })

export const updateProcessType = (processTypeId, name) =>
  apiFetch(`/process-types/${processTypeId}`, { method: 'PUT', body: JSON.stringify({ name }) })

export const deleteProcessType = (processTypeId) =>
  apiFetch(`/process-types/${processTypeId}`, { method: 'DELETE' })

export const listToleranceClasses = (processTypeId) =>
  apiFetch(`/process-types/${processTypeId}/tolerance-classes`)

export const createToleranceClass = (processTypeId, className, value) =>
  apiFetch(`/process-types/${processTypeId}/tolerance-classes`, {
    method: 'POST',
    body: JSON.stringify({ class_name: className, value }),
  })

export const updateToleranceClass = (toleranceClassId, className, value) =>
  apiFetch(`/tolerance-classes/${toleranceClassId}`, {
    method: 'PUT',
    body: JSON.stringify({ class_name: className, value }),
  })

export const deleteToleranceClass = (toleranceClassId) =>
  apiFetch(`/tolerance-classes/${toleranceClassId}`, { method: 'DELETE' })

export const listImages = (analysisId) => apiFetch(`/analyses/${analysisId}/images`)

export async function uploadImage(analysisId, file) {
  const formData = new FormData()
  formData.append('file', file)
  // No Content-Type header here -- the browser sets it (with the right
  // multipart boundary) automatically when the body is a FormData.
  const response = await fetch(`${API_BASE}/analyses/${analysisId}/images`, {
    method: 'POST',
    credentials: 'include',
    body: formData,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed (${response.status})`)
  }
  return response.json()
}

export const deleteImage = (imageId) => apiFetch(`/images/${imageId}`, { method: 'DELETE' })

export const imageFileUrl = (imageId) => `${API_BASE}/images/${imageId}/file`

export const listMarkers = (imageId) => apiFetch(`/images/${imageId}/markers`)

export const createMarker = (imageId, x, y) =>
  apiFetch(`/images/${imageId}/markers`, { method: 'POST', body: JSON.stringify({ x, y }) })

export const deleteMarker = (markerId) => apiFetch(`/markers/${markerId}`, { method: 'DELETE' })
