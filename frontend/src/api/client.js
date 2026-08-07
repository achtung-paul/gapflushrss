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

export const listUsers = (search, page) => {
  const params = new URLSearchParams()
  if (search) params.set('search', search)
  params.set('page', page)
  return apiFetch(`/admin/users?${params.toString()}`)
}

export const createUser = (username, email, password, globalRole) =>
  apiFetch('/admin/users', {
    method: 'POST',
    body: JSON.stringify({ username, email, password, global_role: globalRole }),
  })

export const deleteUser = (userId) => apiFetch(`/admin/users/${userId}`, { method: 'DELETE' })

export const listProjectMembers = (projectId) => apiFetch(`/admin/projects/${projectId}/members`)

export const addProjectMember = (projectId, userId, groupRole) =>
  apiFetch(`/admin/projects/${projectId}/members`, {
    method: 'POST',
    body: JSON.stringify({ user_id: userId, group_role: groupRole }),
  })

export const removeProjectMember = (projectId, groupRole, userId) =>
  apiFetch(`/admin/projects/${projectId}/members/${groupRole}/${userId}`, { method: 'DELETE' })

export const listProjects = () => apiFetch('/projects')

export const createProject = (projectName) =>
  apiFetch('/projects', { method: 'POST', body: JSON.stringify({ project_name: projectName }) })

export const updateProject = (projectId, projectName) =>
  apiFetch(`/projects/${projectId}`, {
    method: 'PUT',
    body: JSON.stringify({ project_name: projectName }),
  })

export const deleteProject = (projectId) => apiFetch(`/projects/${projectId}`, { method: 'DELETE' })

export const listCommodities = (projectId) => apiFetch(`/projects/${projectId}/commodities`)

export const createCommodity = (projectId, name, code) =>
  apiFetch(`/projects/${projectId}/commodities`, {
    method: 'POST',
    body: JSON.stringify({ name, code }),
  })

export const listAnalyses = (commodityId) => apiFetch(`/commodities/${commodityId}/analyses`)

export const getAnalysis = (analysisId) => apiFetch(`/analyses/${analysisId}`)

export const createGapEntry = (analysisId, entry) =>
  apiFetch(`/analyses/${analysisId}/gap`, { method: 'POST', body: JSON.stringify(entry) })

export const createFlushEntry = (analysisId, entry) =>
  apiFetch(`/analyses/${analysisId}/flush`, { method: 'POST', body: JSON.stringify(entry) })

export const updateGapEntry = (analysisId, entry) =>
  apiFetch(`/analyses/${analysisId}/gap`, { method: 'PUT', body: JSON.stringify(entry) })

export const updateFlushEntry = (analysisId, entry) =>
  apiFetch(`/analyses/${analysisId}/flush`, { method: 'PUT', body: JSON.stringify(entry) })

export const deleteEntry = (entryId) => apiFetch(`/entries/${entryId}`, { method: 'DELETE' })

export const listAnalysisImages = (analysisId) => apiFetch(`/analyses/${analysisId}/images`)

export async function uploadAnalysisImage(analysisId, file) {
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

export const deleteAnalysisImage = (analysisImageId) =>
  apiFetch(`/analysis-images/${analysisImageId}`, { method: 'DELETE' })

export const analysisImageFileUrl = (analysisImageId) => `${API_BASE}/analysis-images/${analysisImageId}/file`

export const listProcessTypes = () => apiFetch('/process-types')

export const createProcessType = (name) =>
  apiFetch('/process-types', { method: 'POST', body: JSON.stringify({ name }) })

export const updateProcessType = (processTypeId, name) =>
  apiFetch(`/process-types/${processTypeId}`, { method: 'PUT', body: JSON.stringify({ name }) })

export const deleteProcessType = (processTypeId) =>
  apiFetch(`/process-types/${processTypeId}`, { method: 'DELETE' })

export const listToleranceGroups = (processTypeId) =>
  apiFetch(`/process-types/${processTypeId}/tolerance-groups`)

export const createToleranceGroup = (processTypeId, name) =>
  apiFetch(`/process-types/${processTypeId}/tolerance-groups`, {
    method: 'POST',
    body: JSON.stringify({ name }),
  })

export const updateToleranceGroup = (toleranceGroupId, name) =>
  apiFetch(`/tolerance-groups/${toleranceGroupId}`, {
    method: 'PUT',
    body: JSON.stringify({ name }),
  })

export const deleteToleranceGroup = (toleranceGroupId) =>
  apiFetch(`/tolerance-groups/${toleranceGroupId}`, { method: 'DELETE' })

export const listDimensionRanges = (processTypeId) =>
  apiFetch(`/process-types/${processTypeId}/dimension-ranges`)

export const createDimensionRange = (processTypeId, minValue, maxValue) =>
  apiFetch(`/process-types/${processTypeId}/dimension-ranges`, {
    method: 'POST',
    body: JSON.stringify({ min_value: minValue, max_value: maxValue }),
  })

export const updateDimensionRange = (dimensionRangeId, minValue, maxValue) =>
  apiFetch(`/dimension-ranges/${dimensionRangeId}`, {
    method: 'PUT',
    body: JSON.stringify({ min_value: minValue, max_value: maxValue }),
  })

export const deleteDimensionRange = (dimensionRangeId) =>
  apiFetch(`/dimension-ranges/${dimensionRangeId}`, { method: 'DELETE' })

export const listToleranceValues = (processTypeId) =>
  apiFetch(`/process-types/${processTypeId}/tolerance-values`)

export const setToleranceValueCell = (toleranceGroupId, dimensionRangeId, toolValue, nonToolValue) =>
  apiFetch(`/tolerance-groups/${toleranceGroupId}/dimension-ranges/${dimensionRangeId}/value`, {
    method: 'PUT',
    body: JSON.stringify({ tool_value: toolValue, non_tool_value: nonToolValue }),
  })

export const listImages = (commodityId) => apiFetch(`/commodities/${commodityId}/images`)

export async function uploadImage(commodityId, file) {
  const formData = new FormData()
  formData.append('file', file)
  // No Content-Type header here -- the browser sets it (with the right
  // multipart boundary) automatically when the body is a FormData.
  const response = await fetch(`${API_BASE}/commodities/${commodityId}/images`, {
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

export const createMarker = (imageId, points) =>
  apiFetch(`/images/${imageId}/markers`, { method: 'POST', body: JSON.stringify({ points }) })

export const deleteMarker = (markerId) => apiFetch(`/markers/${markerId}`, { method: 'DELETE' })

export const listChainComponents = (entryId) => apiFetch(`/entries/${entryId}/chain-components`)

export const createChainComponent = (entryId, component) =>
  apiFetch(`/entries/${entryId}/chain-components`, {
    method: 'POST',
    body: JSON.stringify(component),
  })

export const deleteChainComponent = (chainComponentId) =>
  apiFetch(`/chain-components/${chainComponentId}`, { method: 'DELETE' })

export const getSimulation = (entryId) => apiFetch(`/entries/${entryId}/simulation`)
