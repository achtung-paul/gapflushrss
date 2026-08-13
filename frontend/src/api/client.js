// Small wrapper around fetch() for talking to the backend. Nginx proxies
// /api/* to the backend (see nginx/nginx.conf), so a plain relative path
// works both in the Docker deployment and if you ever add a dev proxy.
const API_BASE = '/api'

// Turn a failed response into the best message we can find. Most errors
// are FastAPI's {"detail": "..."} JSON, but not all of them reach the
// backend at all -- nginx rejects an over-sized upload itself and returns
// an HTML error page, which would otherwise surface as a bare
// "Request failed (413)". Falling back to the status text keeps those
// readable.
async function errorMessage(response) {
  const raw = await response.text().catch(() => '')
  try {
    const detail = JSON.parse(raw).detail
    if (detail) {
      // Pydantic validation errors come back as an array of objects
      // rather than a string -- surface the messages, not "[object Object]".
      return Array.isArray(detail) ? detail.map((d) => d.msg || String(d)).join('; ') : detail
    }
  } catch {
    // Not JSON (e.g. nginx's HTML 413 page) -- fall through.
  }
  if (response.status === 413) {
    return 'That file is too large to upload.'
  }
  return `Request failed (${response.status} ${response.statusText})`.trim()
}

async function apiFetch(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    // Send/receive the session cookie.
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })

  if (!response.ok) {
    throw new Error(await errorMessage(response))
  }
  if (response.status === 204) {
    return null
  }
  return response.json()
}

// Returns a LoginResult, not a user -- status is one of "ok" /
// "2fa_required" / "enrollment_required" (see schemas/two_factor.py).
// Only "ok" carries `user`; the other two carry a challenge_token (and,
// for enrollment, otpauth_uri/qr_data_uri) for verifyTwoFactor below.
export const login = (email, password) =>
  apiFetch('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })

export const verifyTwoFactor = (challengeToken, code) =>
  apiFetch('/auth/2fa/verify', {
    method: 'POST',
    body: JSON.stringify({ challenge_token: challengeToken, code }),
  })

export const logout = () => apiFetch('/auth/logout', { method: 'POST' })

export const fetchCurrentUser = () => apiFetch('/auth/me')

export const requestPasswordReset = (email) =>
  apiFetch('/auth/password-reset/request', { method: 'POST', body: JSON.stringify({ email }) })

export const confirmPasswordReset = (token, newPassword) =>
  apiFetch('/auth/password-reset/confirm', {
    method: 'POST',
    body: JSON.stringify({ token, new_password: newPassword }),
  })

// Root admin's own account list -- /admin/root-admins only ever returns
// root_admin accounts (see api/admin.py), so there's no global_role
// param to send: every account created here is a root_admin by definition.
export const listRootAdmins = (search, page) => {
  const params = new URLSearchParams()
  if (search) params.set('search', search)
  params.set('page', page)
  return apiFetch(`/admin/root-admins?${params.toString()}`)
}

// No password -- the account is created with an unusable one and an
// invite email is sent (see core/invites.py). The new admin sets their
// own password by following that link.
export const createRootAdmin = (firstName, lastName, email) =>
  apiFetch('/admin/root-admins', {
    method: 'POST',
    body: JSON.stringify({ first_name: firstName, last_name: lastName, email }),
  })

export const updateRootAdmin = (userId, firstName, lastName, email) =>
  apiFetch(`/admin/root-admins/${userId}`, {
    method: 'PUT',
    body: JSON.stringify({ first_name: firstName, last_name: lastName, email }),
  })

export const deleteRootAdmin = (userId) => apiFetch(`/admin/root-admins/${userId}`, { method: 'DELETE' })

export const resendRootAdminInvite = (userId) =>
  apiFetch(`/admin/root-admins/${userId}/resend-invite`, { method: 'POST' })

export const resetRootAdmin2fa = (userId) =>
  apiFetch(`/admin/root-admins/${userId}/reset-2fa`, { method: 'POST' })

// A client admin's own client's users -- /client-admin/users is scoped
// server-side to current_user.client_id (see api/client_admin.py).
export const listClientUsers = (search, page) => {
  const params = new URLSearchParams()
  if (search) params.set('search', search)
  params.set('page', page)
  return apiFetch(`/client-admin/users?${params.toString()}`)
}

// No password -- see createRootAdmin above.
export const createClientUser = (firstName, lastName, email, globalRole) =>
  apiFetch('/client-admin/users', {
    method: 'POST',
    body: JSON.stringify({
      first_name: firstName,
      last_name: lastName,
      email,
      global_role: globalRole,
    }),
  })

export const updateClientUser = (userId, firstName, lastName, email, globalRole) =>
  apiFetch(`/client-admin/users/${userId}`, {
    method: 'PUT',
    body: JSON.stringify({
      first_name: firstName,
      last_name: lastName,
      email,
      global_role: globalRole,
    }),
  })

export const deleteClientUser = (userId) => apiFetch(`/client-admin/users/${userId}`, { method: 'DELETE' })

export const forceClientUserPasswordReset = (userId) =>
  apiFetch(`/client-admin/users/${userId}/force-password-reset`, { method: 'POST' })

export const resendClientUserInvite = (userId) =>
  apiFetch(`/client-admin/users/${userId}/resend-invite`, { method: 'POST' })

export const resetClientUser2fa = (userId) =>
  apiFetch(`/client-admin/users/${userId}/reset-2fa`, { method: 'POST' })

export const getBanner = () => apiFetch('/banner')

export const updateBanner = (message, colour, isActive) =>
  apiFetch('/admin/banner', {
    method: 'PUT',
    body: JSON.stringify({ message, colour, is_active: isActive }),
  })

export const getSecuritySettings = () => apiFetch('/admin/security-settings')

export const updateSecuritySettings = (require2fa) =>
  apiFetch('/admin/security-settings', {
    method: 'PUT',
    body: JSON.stringify({ require_2fa: require2fa }),
  })

export const listLogs = (service, level, limit) => {
  const params = new URLSearchParams()
  if (service) params.set('service', service)
  if (level) params.set('level', level)
  if (limit) params.set('limit', String(limit))
  return apiFetch(`/admin/logs?${params.toString()}`)
}

// Moved from /admin/projects/... to /client-admin/projects/... -- only a
// client admin can manage their own client's project memberships now
// (see api/client_admin.py).
export const listProjectMembers = (projectId) => apiFetch(`/client-admin/projects/${projectId}/members`)

export const addProjectMember = (projectId, userId, groupRole) =>
  apiFetch(`/client-admin/projects/${projectId}/members`, {
    method: 'POST',
    body: JSON.stringify({ user_id: userId, group_role: groupRole }),
  })

export const removeProjectMember = (projectId, groupRole, userId) =>
  apiFetch(`/client-admin/projects/${projectId}/members/${groupRole}/${userId}`, { method: 'DELETE' })

export const listProjects = () => apiFetch('/projects')

// No service ids -- a project always inherits its client's dedicated
// Postgres/MinIO now (see api/projects.py's create_project); a client
// admin never picks one.
export const createProject = (projectName) =>
  apiFetch('/projects', { method: 'POST', body: JSON.stringify({ project_name: projectName }) })

export const updateProject = (projectId, projectName) =>
  apiFetch(`/projects/${projectId}`, {
    method: 'PUT',
    body: JSON.stringify({ project_name: projectName }),
  })

export const deleteProject = (projectId) => apiFetch(`/projects/${projectId}`, { method: 'DELETE' })

export const listClients = () => apiFetch('/admin/clients')

// postgresServiceId/postgresServerId are mutually exclusive -- pass
// exactly one (same for the minio pair). A *service* id picks an
// already-registered, already-dedicated database/bucket; a *server* id
// asks the backend to provision a brand-new one on that registered
// server instead (see api/admin_clients.py's create_client,
// core/service_provisioning.py). Passed as one options object rather
// than more positional params -- this was already a 7-argument
// function before the auto-provisioning choice doubled the service
// arguments to four.
// No admin_password -- the first client admin gets an invite email too
// (see core/invites.py).
export const createClient = ({
  name,
  postgresServiceId,
  postgresServerId,
  minioServiceId,
  minioServerId,
  adminFirstName,
  adminLastName,
  adminEmail,
}) =>
  apiFetch('/admin/clients', {
    method: 'POST',
    body: JSON.stringify({
      name,
      postgres_service_id: postgresServiceId ?? null,
      postgres_server_id: postgresServerId ?? null,
      minio_service_id: minioServiceId ?? null,
      minio_server_id: minioServerId ?? null,
      admin_first_name: adminFirstName,
      admin_last_name: adminLastName,
      admin_email: adminEmail,
    }),
  })

export const listPostgresServers = () => apiFetch('/admin/postgres-servers')

export const createPostgresServer = (server) =>
  apiFetch('/admin/postgres-servers', { method: 'POST', body: JSON.stringify(server) })

export const deletePostgresServer = (postgresServerId) =>
  apiFetch(`/admin/postgres-servers/${postgresServerId}`, { method: 'DELETE' })

export const listMinioServers = () => apiFetch('/admin/minio-servers')

export const createMinioServer = (server) =>
  apiFetch('/admin/minio-servers', { method: 'POST', body: JSON.stringify(server) })

export const deleteMinioServer = (minioServerId) =>
  apiFetch(`/admin/minio-servers/${minioServerId}`, { method: 'DELETE' })

export const updateClient = (clientId, name, isActive) =>
  apiFetch(`/admin/clients/${clientId}`, {
    method: 'PUT',
    body: JSON.stringify({ name, is_active: isActive }),
  })

export const listClientAdmins = (clientId) => apiFetch(`/admin/clients/${clientId}/admins`)

export const addClientAdmin = (clientId, firstName, lastName, email) =>
  apiFetch(`/admin/clients/${clientId}/admins`, {
    method: 'POST',
    body: JSON.stringify({ first_name: firstName, last_name: lastName, email }),
  })

export const forceClientAdminPasswordReset = (clientId, userId) =>
  apiFetch(`/admin/clients/${clientId}/admins/${userId}/force-password-reset`, { method: 'POST' })

export const resendClientAdminInvite = (clientId, userId) =>
  apiFetch(`/admin/clients/${clientId}/admins/${userId}/resend-invite`, { method: 'POST' })

export const resetClientAdmin2fa = (clientId, userId) =>
  apiFetch(`/admin/clients/${clientId}/admins/${userId}/reset-2fa`, { method: 'POST' })

// Permanent: snapshots the client first, then purges every project,
// user, and the client itself (see api/admin_clients.py's delete_client).
export const deleteClient = (clientId) => apiFetch(`/admin/clients/${clientId}`, { method: 'DELETE' })

export const listPostgresServices = () => apiFetch('/admin/postgres-services')

export const createPostgresService = (service) =>
  apiFetch('/admin/postgres-services', { method: 'POST', body: JSON.stringify(service) })

export const initializePostgresService = (postgresServiceId) =>
  apiFetch(`/admin/postgres-services/${postgresServiceId}/initialize`, { method: 'POST' })

export const deletePostgresService = (postgresServiceId) =>
  apiFetch(`/admin/postgres-services/${postgresServiceId}`, { method: 'DELETE' })

export const listMinioServices = () => apiFetch('/admin/minio-services')

export const createMinioService = (service) =>
  apiFetch('/admin/minio-services', { method: 'POST', body: JSON.stringify(service) })

export const initializeMinioService = (minioServiceId) =>
  apiFetch(`/admin/minio-services/${minioServiceId}/initialize`, { method: 'POST' })

export const deleteMinioService = (minioServiceId) =>
  apiFetch(`/admin/minio-services/${minioServiceId}`, { method: 'DELETE' })

export const listCommodities = (projectId) => apiFetch(`/projects/${projectId}/commodities`)

export const createCommodity = (projectId, name, code) =>
  apiFetch(`/projects/${projectId}/commodities`, {
    method: 'POST',
    body: JSON.stringify({ name, code }),
  })

export const listAnalyses = (projectId, commodityId) =>
  apiFetch(`/projects/${projectId}/commodities/${commodityId}/analyses`)

export const getAnalysis = (projectId, analysisId) => apiFetch(`/projects/${projectId}/analyses/${analysisId}`)

export const updateAnalysisDescription = (projectId, analysisId, description) =>
  apiFetch(`/projects/${projectId}/analyses/${analysisId}`, {
    method: 'PUT',
    body: JSON.stringify({ description }),
  })

export const createGapEntry = (projectId, analysisId, entry) =>
  apiFetch(`/projects/${projectId}/analyses/${analysisId}/gap`, {
    method: 'POST',
    body: JSON.stringify(entry),
  })

export const createFlushEntry = (projectId, analysisId, entry) =>
  apiFetch(`/projects/${projectId}/analyses/${analysisId}/flush`, {
    method: 'POST',
    body: JSON.stringify(entry),
  })

export const updateGapEntry = (projectId, analysisId, entry) =>
  apiFetch(`/projects/${projectId}/analyses/${analysisId}/gap`, {
    method: 'PUT',
    body: JSON.stringify(entry),
  })

export const updateFlushEntry = (projectId, analysisId, entry) =>
  apiFetch(`/projects/${projectId}/analyses/${analysisId}/flush`, {
    method: 'PUT',
    body: JSON.stringify(entry),
  })

export const deleteEntry = (projectId, entryId) =>
  apiFetch(`/projects/${projectId}/entries/${entryId}`, { method: 'DELETE' })

// entryId -- these images belong to a specific Gap or Flush entry, not
// the whole Analysis, so Gap and Flush each get their own gallery (see
// api/analysis_images.py).
export const listAnalysisImages = (projectId, entryId) =>
  apiFetch(`/projects/${projectId}/entries/${entryId}/images`)

export async function uploadAnalysisImage(projectId, entryId, file) {
  const formData = new FormData()
  formData.append('file', file)
  // No Content-Type header here -- the browser sets it (with the right
  // multipart boundary) automatically when the body is a FormData.
  const response = await fetch(`${API_BASE}/projects/${projectId}/entries/${entryId}/images`, {
    method: 'POST',
    credentials: 'include',
    body: formData,
  })
  if (!response.ok) {
    throw new Error(await errorMessage(response))
  }
  return response.json()
}

export const deleteAnalysisImage = (projectId, analysisImageId) =>
  apiFetch(`/projects/${projectId}/analysis-images/${analysisImageId}`, { method: 'DELETE' })

export const analysisImageFileUrl = (projectId, analysisImageId) =>
  `${API_BASE}/projects/${projectId}/analysis-images/${analysisImageId}/file`

export const entryExportUrl = (projectId, entryId) =>
  `${API_BASE}/projects/${projectId}/entries/${entryId}/export`

export const commodityExportUrl = (projectId, commodityId) =>
  `${API_BASE}/projects/${projectId}/commodities/${commodityId}/export`

export const listProcessTypes = () => apiFetch('/process-types')

export const createProcessType = (name) =>
  apiFetch('/process-types', { method: 'POST', body: JSON.stringify({ name }) })

export async function importProcessType(name, file) {
  const formData = new FormData()
  formData.append('name', name)
  formData.append('file', file)
  // No Content-Type header -- the browser sets it (with the right
  // multipart boundary) automatically when the body is a FormData, same
  // as uploadAnalysisImage below.
  const response = await fetch(`${API_BASE}/process-types/import`, {
    method: 'POST',
    credentials: 'include',
    body: formData,
  })
  if (!response.ok) {
    throw new Error(await errorMessage(response))
  }
  return response.json()
}

export const importTemplateUrl = `${API_BASE}/process-types/import-template`

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

export const listImages = (projectId, commodityId) =>
  apiFetch(`/projects/${projectId}/commodities/${commodityId}/images`)

export async function uploadImage(projectId, commodityId, file) {
  const formData = new FormData()
  formData.append('file', file)
  // No Content-Type header here -- the browser sets it (with the right
  // multipart boundary) automatically when the body is a FormData.
  const response = await fetch(`${API_BASE}/projects/${projectId}/commodities/${commodityId}/images`, {
    method: 'POST',
    credentials: 'include',
    body: formData,
  })
  if (!response.ok) {
    throw new Error(await errorMessage(response))
  }
  return response.json()
}

export const deleteImage = (projectId, imageId) =>
  apiFetch(`/projects/${projectId}/images/${imageId}`, { method: 'DELETE' })

export const imageFileUrl = (projectId, imageId) => `${API_BASE}/projects/${projectId}/images/${imageId}/file`

export const listMarkers = (projectId, imageId) => apiFetch(`/projects/${projectId}/images/${imageId}/markers`)

export const createMarker = (projectId, imageId, points) =>
  apiFetch(`/projects/${projectId}/images/${imageId}/markers`, {
    method: 'POST',
    body: JSON.stringify({ points }),
  })

export const deleteMarker = (projectId, markerId) =>
  apiFetch(`/projects/${projectId}/markers/${markerId}`, { method: 'DELETE' })

export const listChainComponents = (projectId, entryId) =>
  apiFetch(`/projects/${projectId}/entries/${entryId}/chain-components`)

export const createChainComponent = (projectId, entryId, component) =>
  apiFetch(`/projects/${projectId}/entries/${entryId}/chain-components`, {
    method: 'POST',
    body: JSON.stringify(component),
  })

export const updateChainComponent = (projectId, chainComponentId, component) =>
  apiFetch(`/projects/${projectId}/chain-components/${chainComponentId}`, {
    method: 'PUT',
    body: JSON.stringify(component),
  })

export const deleteChainComponent = (projectId, chainComponentId) =>
  apiFetch(`/projects/${projectId}/chain-components/${chainComponentId}`, { method: 'DELETE' })

export const getSimulation = (projectId, entryId) =>
  apiFetch(`/projects/${projectId}/entries/${entryId}/simulation`)

export const listAngledComponents = (projectId, entryId) =>
  apiFetch(`/projects/${projectId}/entries/${entryId}/angled-components`)

export const createAngledComponent = (projectId, entryId, component) =>
  apiFetch(`/projects/${projectId}/entries/${entryId}/angled-components`, {
    method: 'POST',
    body: JSON.stringify(component),
  })

export const updateAngledComponent = (projectId, angledComponentId, component) =>
  apiFetch(`/projects/${projectId}/angled-components/${angledComponentId}`, {
    method: 'PUT',
    body: JSON.stringify(component),
  })

export const deleteAngledComponent = (projectId, angledComponentId) =>
  apiFetch(`/projects/${projectId}/angled-components/${angledComponentId}`, { method: 'DELETE' })

export const getAngledSimulation = (projectId, entryId) =>
  apiFetch(`/projects/${projectId}/entries/${entryId}/angled-simulation`)

export const updateAngledSettings = (projectId, entryId, interfaceAngle, calculationMethod) =>
  apiFetch(`/projects/${projectId}/entries/${entryId}/angled-settings`, {
    method: 'PUT',
    body: JSON.stringify({ interface_angle: interfaceAngle, calculation_method: calculationMethod }),
  })

export const listStandardTolerances = (projectId) =>
  apiFetch(`/projects/${projectId}/standard-tolerances`)

export const createStandardTolerance = (projectId, name, toleranceValue, contributorType) =>
  apiFetch(`/projects/${projectId}/standard-tolerances`, {
    method: 'POST',
    body: JSON.stringify({ name, tolerance_value: toleranceValue, contributor_type: contributorType }),
  })

export const updateStandardTolerance = (projectId, standardToleranceId, name, toleranceValue, contributorType) =>
  apiFetch(`/projects/${projectId}/standard-tolerances/${standardToleranceId}`, {
    method: 'PUT',
    body: JSON.stringify({ name, tolerance_value: toleranceValue, contributor_type: contributorType }),
  })

export const deleteStandardTolerance = (projectId, standardToleranceId) =>
  apiFetch(`/projects/${projectId}/standard-tolerances/${standardToleranceId}`, { method: 'DELETE' })
