import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../boot/api'
import { buildCableRows } from '@/utils/cables'

export const useReportsStore = defineStore('reports', () => {
  const reportTypes = ref([])
  const templates = ref([])
  const letterheads = ref([])

  async function fetchTypes(locale = 'en') {
    const { data } = await api.get('/reports/types', { params: { locale } })
    reportTypes.value = data
    return data
  }

  async function fetchTemplates(params = {}) {
    const { data } = await api.get('/reports/templates', { params })
    templates.value = data
    return data
  }

  async function createTemplate(payload) {
    const { data } = await api.post('/reports/templates', payload)
    templates.value = [...templates.value, data]
    return data
  }

  async function updateTemplate(id, payload) {
    const { data } = await api.put(`/reports/templates/${id}`, payload)
    templates.value = templates.value.map((template) => (template.id === id ? data : template))
    return data
  }

  async function deleteTemplate(id) {
    await api.delete(`/reports/templates/${id}`)
    templates.value = templates.value.filter((template) => template.id !== id)
  }

  async function fetchLetterheads() {
    const { data } = await api.get('/reports/letterheads')
    letterheads.value = data
    return data
  }

  async function uploadLetterhead(file, payload) {
    const form = new FormData()
    form.append('file', file)
    Object.entries(payload).forEach(([key, value]) => {
      if (value !== undefined && value !== null) form.append(key, String(value))
    })
    const { data } = await api.post('/reports/letterheads/upload', form)
    letterheads.value = [...letterheads.value, data]
    return data
  }

  async function updateLetterhead(id, payload) {
    const { data } = await api.put(`/reports/letterheads/${id}`, payload)
    letterheads.value = letterheads.value.map((letterhead) =>
      letterhead.id === id ? data : { ...letterhead, is_default: payload.is_default ? false : letterhead.is_default },
    )
    return data
  }

  async function deleteLetterhead(id) {
    await api.delete(`/reports/letterheads/${id}`)
    letterheads.value = letterheads.value.filter((letterhead) => letterhead.id !== id)
  }

  async function fetchLetterheadPreview(id) {
    const { data } = await api.get(`/reports/letterheads/${id}/preview`, { responseType: 'blob' })
    return data
  }

  async function fetchJobs() {
    const { data } = await api.get('/jobs')
    return data
  }

  async function fetchStagePlotElements(jobId) {
    const { data } = await api.get(`/jobs/${jobId}/plot-elements`)
    return data
  }

  async function fetchStagePlotData(jobId, cablePlan = {}) {
    const [{ data: elements }, { data: lists }, { data: devices }] = await Promise.all([
      api.get(`/jobs/${jobId}/plot-elements`),
      api.get(`/jobs/${jobId}/channel-lists`),
      api.get(`/jobs/${jobId}/devices`),
    ])
    const cables = buildCableRows({ lists, devices, elements, plan: cablePlan })
      .filter((cable) => cable.placed && !cable.hidden)
      .map(({ key, points }) => ({ id: key, points }))
    return { elements, cables }
  }

  async function fetchPatchSheets(jobId) {
    const { data } = await api.get(`/jobs/${jobId}/patch-sheets`)
    return data
  }

  async function fetchPreview(jobId, template, responseType = 'blob', options = {}) {
    const { data } = await api.get(
      `/reports/jobs/${jobId}/${template.domain}/${template.report_type}/preview`,
      {
        params: {
          template_id: template.id,
          ...options,
        },
        responseType,
      },
    )
    return data
  }

  async function generate(jobId, reportType, templateId = null, options = {}) {
    const { data, headers } = await api.get(
      `/reports/jobs/${jobId}/${reportType.domain}/${reportType.report_type}/pdf`,
      {
        params: {
          ...(templateId ? { template_id: templateId } : {}),
          ...options,
        },
        responseType: 'blob',
      },
    )
    return { data, filename: headers['content-disposition']?.match(/filename="([^"]+)"/)?.[1] }
  }

  return {
    reportTypes,
    templates,
    letterheads,
    fetchTypes,
    fetchTemplates,
    createTemplate,
    updateTemplate,
    deleteTemplate,
    fetchLetterheads,
    uploadLetterhead,
    updateLetterhead,
    deleteLetterhead,
    fetchLetterheadPreview,
    fetchJobs,
    fetchStagePlotElements,
    fetchStagePlotData,
    fetchPatchSheets,
    fetchPreview,
    generate,
  }
})
