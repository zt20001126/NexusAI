import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  deleteStagedResumePhoto,
  getResume,
  getSavedResumePhoto,
  saveResume,
  uploadResumePhoto,
} from '../api/resume'
import { createDefaultDraft, type BasicInfo, type ResumeDraft, type ResumeResponse } from '../model/types'

interface LocalPhotoPreview {
  photoId: string
  objectUrl: string
}

export function useResumeEditor() {
  const [draft, setDraft] = useState<ResumeDraft>(createDefaultDraft)
  const [savedResume, setSavedResume] = useState<ResumeResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [uploadingPhoto, setUploadingPhoto] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [photoError, setPhotoError] = useState<string | null>(null)
  const [photoPreviewUrl, setPhotoPreviewUrl] = useState<string | null>(null)
  const localPhotoRef = useRef<LocalPhotoPreview | null>(null)

  const dirty = useMemo(() => {
    if (!savedResume) return false
    return JSON.stringify(draft.content) !== JSON.stringify(savedResume.content)
      || JSON.stringify(draft.style_config) !== JSON.stringify(savedResume.style_config)
  }, [draft, savedResume])

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const response = await getResume()
      setSavedResume(response)
      setDraft({
        content: structuredClone(response.content),
        style_config: structuredClone(response.style_config),
      })
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : '简历加载失败，请重试。')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  useEffect(() => {
    const photoId = draft.content.basic_info.photo_id
    const localPhoto = localPhotoRef.current
    if (localPhoto && localPhoto.photoId === photoId) {
      setPhotoPreviewUrl(localPhoto.objectUrl)
      return
    }
    if (!photoId) {
      setPhotoPreviewUrl(null)
      return
    }

    let cancelled = false
    let loadedUrl: string | null = null
    void getSavedResumePhoto()
      .then((blob) => {
        loadedUrl = URL.createObjectURL(blob)
        if (cancelled) {
          URL.revokeObjectURL(loadedUrl)
          return
        }
        setPhotoPreviewUrl(loadedUrl)
      })
      .catch(() => {
        if (!cancelled) setPhotoPreviewUrl(null)
      })
    return () => {
      cancelled = true
      if (loadedUrl) URL.revokeObjectURL(loadedUrl)
    }
  }, [draft.content.basic_info.photo_id])

  useEffect(() => {
    function warnBeforeUnload(event: BeforeUnloadEvent) {
      if (!dirty) return
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warnBeforeUnload)
    return () => window.removeEventListener('beforeunload', warnBeforeUnload)
  }, [dirty])

  useEffect(() => () => {
    const stagedPhoto = localPhotoRef.current
    if (!stagedPhoto) return
    URL.revokeObjectURL(stagedPhoto.objectUrl)
    void deleteStagedResumePhoto(stagedPhoto.photoId).catch(() => undefined)
  }, [])

  function updateBasicInfo(value: BasicInfo) {
    setDraft((current) => ({ ...current, content: { ...current.content, basic_info: value } }))
  }

  function updateContent<K extends keyof ResumeDraft['content']>(field: K, value: ResumeDraft['content'][K]) {
    setDraft((current) => ({ ...current, content: { ...current.content, [field]: value } }))
  }

  function updateStyle<K extends keyof ResumeDraft['style_config']>(field: K, value: ResumeDraft['style_config'][K]) {
    setDraft((current) => ({ ...current, style_config: { ...current.style_config, [field]: value } }))
  }

  function clearSaveError() {
    setSaveError(null)
  }

  function updateStyleConfig(value: ResumeDraft['style_config']) {
    setDraft((current) => ({ ...current, style_config: value }))
  }

  async function uploadPhoto(file: File) {
    setPhotoError(null)
    if (!['image/png', 'image/jpeg'].includes(file.type)) {
      setPhotoError('请选择 PNG 或 JPEG 图片。')
      return
    }
    if (file.size <= 0 || file.size > 5 * 1024 * 1024) {
      setPhotoError('图片不能为空，且不能超过 5 MiB。')
      return
    }

    setUploadingPhoto(true)
    try {
      const result = await uploadResumePhoto(file)
      const previous = localPhotoRef.current
      if (previous) {
        URL.revokeObjectURL(previous.objectUrl)
        void deleteStagedResumePhoto(previous.photoId).catch(() => undefined)
      }
      const objectUrl = URL.createObjectURL(file)
      localPhotoRef.current = { photoId: result.photo_id, objectUrl }
      setPhotoPreviewUrl(objectUrl)
      setDraft((current) => ({
        ...current,
        content: {
          ...current.content,
          basic_info: { ...current.content.basic_info, photo_id: result.photo_id },
        },
      }))
    } catch (error) {
      setPhotoError(error instanceof Error ? error.message : '照片上传失败，请重试。')
    } finally {
      setUploadingPhoto(false)
    }
  }

  function removePhoto() {
    const photoId = draft.content.basic_info.photo_id
    const localPhoto = localPhotoRef.current
    if (localPhoto && localPhoto.photoId === photoId) {
      URL.revokeObjectURL(localPhoto.objectUrl)
      localPhotoRef.current = null
      void deleteStagedResumePhoto(localPhoto.photoId).catch(() => undefined)
    }
    setPhotoPreviewUrl(null)
    updateBasicInfo({ ...draft.content.basic_info, photo_id: null })
  }

  async function save(): Promise<boolean> {
    if (!savedResume || !dirty || saving) return !dirty
    setSaving(true)
    setSaveError(null)
    try {
      const response = await saveResume(draft)
      setSavedResume(response)
      setDraft({
        content: structuredClone(response.content),
        style_config: structuredClone(response.style_config),
      })
      return true
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : '保存失败，请重试。')
      return false
    } finally {
      setSaving(false)
    }
  }

  function confirmLeave(): boolean {
    return !dirty || window.confirm('简历有尚未保存的修改，确定离开吗？')
  }

  return {
    draft,
    savedResume,
    loading,
    saving,
    uploadingPhoto,
    dirty,
    loadError,
    saveError,
    clearSaveError,
    photoError,
    photoPreviewUrl,
    load,
    save,
    confirmLeave,
    updateBasicInfo,
    updateContent,
    updateStyle,
    updateStyleConfig,
    uploadPhoto,
    removePhoto,
  }
}
