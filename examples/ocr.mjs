import { createWorker } from 'tesseract.js';

async function main() {
  if (process.argv.length < 3) {
    console.error('Usage: node examples/ocr.mjs <image>');
    process.exit(1);
  }

  const imagePath = process.argv[2];
  const worker = await createWorker('eng');

  try {
    const {
      data: { text },
    } = await worker.recognize(imagePath);
    console.log(text);
  } catch (err) {
    console.error('OCR error:', err);
  } finally {
    await worker.terminate();
  }
}

main();
