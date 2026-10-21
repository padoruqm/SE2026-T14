const ALLOWED_EXTENSIONS = ['.las', '.laz']

// Early feedback only; the server remains the source of truth (signature, size).
export function validateUploadFile(file: File): string | null {
  const name = file.name.toLowerCase()
  if (!ALLOWED_EXTENSIONS.some((extension) => name.endsWith(extension))) {
    return 'Only .las and .laz files are supported.'
  }
  if (file.size === 0) {
    return 'The selected file is empty.'
  }
  return null
}
