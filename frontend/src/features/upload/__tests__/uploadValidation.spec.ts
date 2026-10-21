import { describe, expect, it } from 'vitest'

import { validateUploadFile } from '../uploadValidation'

function fileNamed(name: string, content = 'LASF') {
  return new File([content], name)
}

describe('validateUploadFile', () => {
  it.each(['scan.las', 'scan.LAS', 'scan.laz'])('accepts %s', (name) => {
    expect(validateUploadFile(fileNamed(name))).toBeNull()
  })

  it('rejects unsupported extensions', () => {
    expect(validateUploadFile(fileNamed('notes.txt'))).toBe(
      'Only .las and .laz files are supported.',
    )
  })

  it('rejects empty files', () => {
    expect(validateUploadFile(fileNamed('scan.las', ''))).toBe('The selected file is empty.')
  })
})
