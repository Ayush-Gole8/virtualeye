import React, { useState, useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useLocation } from 'react-router-dom';
import { BookOpen, Camera, X, Copy, Trash2, Play, Pause, Download, RotateCcw, Link, FileText, Upload } from 'lucide-react';
import { useVoice } from '../context/VoiceNavigationContext';
import toast from 'react-hot-toast';
import './VisionPage.css';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';

// Helper to add ngrok bypass header
const getFetchOptions = (options = {}) => {
  const isNgrok = API_BASE_URL.includes('ngrok');
  return {
    ...options,
    headers: {
      'ngrok-skip-browser-warning': 'true',  // Bypass ngrok warning page
      ...options.headers,
    },
  };
};

const OCRPage = () => {
  const { speak } = useVoice();
  const location = useLocation();
  
  const [isStreaming, setIsStreaming] = useState(false);
  const [ocrText, setOcrText] = useState('');
  const [ocrInProgress, setOcrInProgress] = useState(false);
  const [currentFrame, setCurrentFrame] = useState(null);
  const [ocrLang, setOcrLang] = useState('en');
  const [autoOCR, setAutoOCR] = useState(false);
  const [textHistory, setTextHistory] = useState([]);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [speechRate, setSpeechRate] = useState(1.0);
  const [inputMode, setInputMode] = useState('camera'); // 'camera', 'url', 'pdf'
  const [urlInput, setUrlInput] = useState('');
  const [pdfFile, setPdfFile] = useState(null);
  const [isProcessingUrl, setIsProcessingUrl] = useState(false);
  const [isProcessingPdf, setIsProcessingPdf] = useState(false);
  
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const canvasRef = useRef(null);
  const intervalRef = useRef(null);
  const autoOCRIntervalRef = useRef(null);
  const speechUtteranceRef = useRef(null);
  const fileInputRef = useRef(null);

  // Start camera
  const startCamera = async () => {
    try {
      speak("Starting camera for text reading.");
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 } }
      });
      
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        streamRef.current = stream;
        setIsStreaming(true);
        toast.success('Camera started');
      }
    } catch (err) {
      console.error('Error accessing camera:', err);
      toast.error('Could not access camera. Check permissions.');
      speak("I cannot access the camera. Please check permissions.");
    }
  };

  // Stop camera
  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
      setIsStreaming(false);
      setAutoOCR(false);
      if (autoOCRIntervalRef.current) {
        clearInterval(autoOCRIntervalRef.current);
        autoOCRIntervalRef.current = null;
      }
      toast.success('Camera stopped');
      speak("Camera stopped.");
    }
  };

  // Capture frame from video
  const captureFrame = () => {
    if (videoRef.current && canvasRef.current) {
      const ctx = canvasRef.current.getContext('2d');
      canvasRef.current.width = videoRef.current.videoWidth;
      canvasRef.current.height = videoRef.current.videoHeight;
      ctx.drawImage(videoRef.current, 0, 0);
      return canvasRef.current.toDataURL('image/jpeg', 0.9);
    }
    return null;
  };

  // Process OCR from image blob
  const processOCRFromBlob = async (blob, silent = false) => {
    if (ocrInProgress) return; // Prevent multiple simultaneous requests

    setOcrInProgress(true);
    
    try {
      // Send to backend
      const formData = new FormData();
      formData.append('frame', blob);
      formData.append('langs', ocrLang);

      const res = await fetch(`${API_BASE_URL}/ocr`, getFetchOptions({
        method: 'POST',
        body: formData,
      }));

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({ error: res.statusText }));
        throw new Error(`Backend error: ${errorData.error || res.statusText}`);
      }

      const data = await res.json();
      
      if (data.text && data.text.trim()) {
        const cleanedText = data.text.trim();
        setOcrText(cleanedText);
        
        // Add to history
        setTextHistory(prev => {
          const newHistory = [{ text: cleanedText, timestamp: new Date(), lang: data.languages || ocrLang, source: inputMode }, ...prev];
          return newHistory.slice(0, 10); // Keep last 10
        });
        
        if (!silent) {
          const langStr = data.languages?.join(' and ') || ocrLang;
          speak(`Found text in ${langStr}. ${cleanedText.length > 100 ? cleanedText.substring(0, 100) + '...' : cleanedText}`);
          toast.success(`Extracted ${data.line_count || 1} line(s) of text`);
        }
        return true;
      } else {
        if (!silent) {
          setOcrText('No text detected in the image.');
          speak('No text found in the image.');
          toast('No text detected', { icon: 'ℹ️' });
        }
        return false;
      }
    } catch (err) {
      console.error('[OCR] Error:', err);
      const errorMsg = err.message || 'Unknown OCR error';
      if (!silent) {
        toast.error(`OCR failed: ${errorMsg}`);
        speak(`Text extraction failed: ${errorMsg}`);
      }
      if (!ocrText) setOcrText('');
      return false;
    } finally {
      setOcrInProgress(false);
    }
  };

  // Handle OCR from camera
  const handleOCR = async (silent = false) => {
    if (!isStreaming) {
      if (!silent) {
        toast.error('Camera not active. Start camera first.');
        speak("Camera not active. Please start the camera first.");
      }
      return;
    }

    try {
      // Capture frame
      const frameData = captureFrame();
      if (!frameData) {
        throw new Error('Failed to capture frame');
      }

      // Convert to blob
      const response = await fetch(frameData);
      const blob = await response.blob();

      await processOCRFromBlob(blob, silent);
    } catch (err) {
      console.error('[OCR] Error:', err);
      if (!silent) {
        toast.error(`Failed to capture frame: ${err.message}`);
      }
    }
  };

  // Handle OCR from URL
  const handleOCRFromURL = async () => {
    if (!urlInput.trim()) {
      toast.error('Please enter a valid image URL');
      speak("Please enter a valid image URL.");
      return;
    }

    // Validate URL format
    let url;
    try {
      url = new URL(urlInput.trim());
    } catch (e) {
      toast.error('Invalid URL format. Please enter a complete URL (e.g., https://example.com/image.jpg)');
      speak("Invalid URL format. Please enter a complete URL.");
      return;
    }

    // Check if URL looks like an image (basic check)
    const imageExtensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg'];
    const pathLower = url.pathname.toLowerCase();
    const isImageUrl = imageExtensions.some(ext => pathLower.endsWith(ext)) || 
                      urlInput.includes('/image') || 
                      urlInput.includes('imgur') ||
                      urlInput.includes('i.imgur');

    if (!isImageUrl) {
      toast.error('This does not appear to be an image URL. Please use a direct link to an image file (JPG, PNG, etc.)', { duration: 6000 });
      speak("This URL does not appear to be an image. Please use a direct link to an image file.");
      toast('Examples: https://example.com/image.jpg or https://i.imgur.com/abc123.png', { icon: '💡', duration: 6000 });
      return;
    }

    setIsProcessingUrl(true);
    setOcrInProgress(true);
    
    try {
      speak("Fetching image from URL.");
      toast('Fetching image from URL...', { icon: '⏳' });
      
      // Always use backend proxy to avoid CORS issues
      console.log('[OCR URL] Using backend proxy to fetch image...');
      const proxyFormData = new FormData();
      proxyFormData.append('url', urlInput.trim());
      proxyFormData.append('langs', ocrLang);
      
      const proxyRes = await fetch(`${API_BASE_URL}/ocr_url`, getFetchOptions({
        method: 'POST',
        body: proxyFormData,
      }));
      
      if (!proxyRes.ok) {
        const errorData = await proxyRes.json().catch(() => ({ error: proxyRes.statusText }));
        const errorMsg = errorData.error || proxyRes.statusText;
        
        // Provide helpful error messages
        if (errorMsg.includes('403') || errorMsg.includes('Forbidden')) {
          throw new Error('Access denied (403). The URL may require authentication or block automated access. Try a public image URL.');
        } else if (errorMsg.includes('404')) {
          throw new Error('Image not found (404). Please check the URL.');
        } else if (errorMsg.includes('does not point to an image')) {
          throw new Error('URL does not point to an image. Please use a direct image link (JPG, PNG, etc.)');
        } else {
          throw new Error(errorMsg);
        }
      }
      
      const data = await proxyRes.json();
      
      if (data.text && data.text.trim()) {
        const cleanedText = data.text.trim();
        setOcrText(cleanedText);
        setTextHistory(prev => {
          const newHistory = [{ text: cleanedText, timestamp: new Date(), lang: data.languages || ocrLang, source: 'url' }, ...prev];
          return newHistory.slice(0, 10);
        });
        const langStr = data.languages?.join(' and ') || ocrLang;
        speak(`Found text in ${langStr}. ${cleanedText.length > 100 ? cleanedText.substring(0, 100) + '...' : cleanedText}`);
        toast.success(`Extracted ${data.line_count || 1} line(s) of text`);
        setUrlInput('');
      } else {
        setOcrText('No text detected in the image.');
        speak('No text found in the image.');
        toast('No text detected', { icon: 'ℹ️' });
      }
    } catch (err) {
      console.error('[OCR URL] Error:', err);
      const errorMsg = err.message || 'Unknown error';
      toast.error(`Failed to extract from URL: ${errorMsg}`, { duration: 6000 });
      speak(`Failed to extract text from URL: ${errorMsg}`);
      
      // Helpful tips
      if (errorMsg.includes('403') || errorMsg.includes('Forbidden')) {
        toast('Tip: Use public image hosting services like Imgur, or direct image links ending in .jpg, .png, etc.', { icon: '💡', duration: 6000 });
      } else if (errorMsg.includes('does not point to an image')) {
        toast('Tip: The URL should point directly to an image file, not a webpage. Try right-clicking an image and selecting "Copy image address".', { icon: '💡', duration: 6000 });
      }
    } finally {
      setIsProcessingUrl(false);
      setOcrInProgress(false);
    }
  };

  // Handle PDF file upload
  const handlePDFUpload = async (file) => {
    if (!file) return;

    if (file.type !== 'application/pdf') {
      toast.error('Please upload a PDF file');
      speak("Please upload a PDF file.");
      return;
    }

    setIsProcessingPdf(true);
    setOcrInProgress(true);
    
    try {
      speak("Processing PDF file.");
        toast('Processing PDF... This may take a moment.', { icon: '⏳' });
      
      // Create a form data with PDF
      const formData = new FormData();
      formData.append('pdf', file);
      formData.append('langs', ocrLang);

      const res = await fetch(`${API_BASE_URL}/ocr_pdf`, getFetchOptions({
        method: 'POST',
        body: formData,
      }));

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({ error: res.statusText }));
        const errorMsg = errorData.error || res.statusText;
        
        // Check if it's a missing dependency error
        if (errorMsg.includes('pdf2image') || errorMsg.includes('poppler')) {
          throw new Error('PDF processing requires pdf2image library. Install in backend: pip install pdf2image');
        }
        
        throw new Error(`Backend error: ${errorMsg}`);
      }

      const data = await res.json();
      
      if (data.text && data.text.trim()) {
        const cleanedText = data.text.trim();
        setOcrText(cleanedText);
        
        setTextHistory(prev => {
          const newHistory = [{ text: cleanedText, timestamp: new Date(), lang: data.languages || ocrLang, source: 'pdf' }, ...prev];
          return newHistory.slice(0, 10);
        });
        
        const langStr = data.languages?.join(' and ') || ocrLang;
        const pageInfo = data.pages_processed ? ` from ${data.pages_processed} page(s)` : '';
        speak(`Extracted text from PDF${pageInfo} in ${langStr}. ${cleanedText.length > 100 ? cleanedText.substring(0, 100) + '...' : cleanedText}`);
        toast.success(`Extracted ${data.line_count || 1} line(s) from PDF${pageInfo}`);
        setPdfFile(null);
      } else {
        setOcrText('No text detected in the PDF.');
        speak('No text found in the PDF.');
        toast('No text detected in PDF', { icon: 'ℹ️' });
      }
    } catch (err) {
      console.error('[OCR PDF] Error:', err);
      const errorMsg = err.message || 'Unknown error';
      toast.error(`PDF processing failed: ${errorMsg}`);
      speak(`PDF processing failed: ${errorMsg}`);
      
      // Show helpful message
      if (errorMsg.includes('pdf2image')) {
        toast('Backend needs: pip install pdf2image pillow. Also install poppler-utils on system.', { icon: '💡', duration: 6000 });
      } else {
        toast('Tip: Convert PDF pages to images and use URL or camera mode', { icon: '💡', duration: 5000 });
      }
    } finally {
      setIsProcessingPdf(false);
      setOcrInProgress(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  // Handle file selection
  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (file) {
      setPdfFile(file);
      handlePDFUpload(file);
    }
  };

  // Toggle auto-OCR
  const toggleAutoOCR = () => {
    if (!isStreaming) {
      toast.error('Start camera first');
      return;
    }
    
    setAutoOCR(prev => {
      const newState = !prev;
      if (newState) {
        // Start auto-OCR every 3 seconds
        handleOCR(true); // First one immediately
        autoOCRIntervalRef.current = setInterval(() => {
          handleOCR(true);
        }, 3000);
        speak("Auto text reading started. Reading every 3 seconds.");
      } else {
        // Stop auto-OCR
        if (autoOCRIntervalRef.current) {
          clearInterval(autoOCRIntervalRef.current);
          autoOCRIntervalRef.current = null;
        }
        speak("Auto text reading stopped.");
      }
      return newState;
    });
  };

  // Copy text to clipboard
  const copyToClipboard = async () => {
    if (!ocrText) {
      toast.error('No text to copy');
      return;
    }
    try {
      await navigator.clipboard.writeText(ocrText);
      toast.success('Text copied to clipboard!');
      speak("Text copied to clipboard.");
    } catch (err) {
      toast.error('Failed to copy text');
      speak("Failed to copy text.");
    }
  };

  // Clear text
  const clearText = () => {
    setOcrText('');
    toast('Text cleared', { icon: '🗑️' });
    speak("Text cleared.");
  };

  // Download text as file
  const downloadText = () => {
    if (!ocrText) {
      toast.error('No text to download');
      return;
    }
    const blob = new Blob([ocrText], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ocr-text-${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast.success('Text downloaded!');
    speak("Text downloaded.");
  };

  // Speak text with controls
  const speakText = () => {
    if (!ocrText) {
      toast.error('No text to speak');
      return;
    }
    
    if (isSpeaking) {
      // Stop speaking
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
      speak("Stopped reading.");
    } else {
      // Start speaking
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(ocrText);
      utterance.rate = speechRate;
      utterance.onend = () => setIsSpeaking(false);
      utterance.onerror = () => setIsSpeaking(false);
      window.speechSynthesis.speak(utterance);
      setIsSpeaking(true);
    }
  };

  // Voice commands for OCR
  useEffect(() => {
    if (!location.pathname.includes('ocr')) return;

    const handleVoiceRead = () => {
      if (!isStreaming) {
        startCamera();
        setTimeout(() => handleOCR(false), 1500);
      } else {
        handleOCR(false);
      }
    };

    const handleVoiceAutoRead = () => {
      if (isStreaming) {
        toggleAutoOCR();
      } else {
        speak("Please start the camera first for auto reading.");
      }
    };

    window.addEventListener('voice-read-text', handleVoiceRead);
    window.addEventListener('voice-auto-read', handleVoiceAutoRead);

    return () => {
      window.removeEventListener('voice-read-text', handleVoiceRead);
      window.removeEventListener('voice-auto-read', handleVoiceAutoRead);
    };
  }, [location.pathname, isStreaming]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
      }
      if (autoOCRIntervalRef.current) {
        clearInterval(autoOCRIntervalRef.current);
      }
      window.speechSynthesis.cancel();
    };
  }, []);

  return (
    <div className="vision-container">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="vision-content"
      >
        {/* Header */}
        <div className="vision-header">
          <div className="flex items-center gap-3">
            <div className="icon-badge">
              <BookOpen size={32} />
            </div>
            <div>
              <h1 className="vision-title">Read Text (OCR)</h1>
              <p className="vision-subtitle">Extract text from camera view using EasyOCR</p>
            </div>
          </div>
        </div>

        {/* Main Content */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Camera Section */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="video-container"
          >
            <video
              ref={videoRef}
              autoPlay
              playsInline
              className="video-stream"
              style={{ display: isStreaming ? 'block' : 'none' }}
            />
            {!isStreaming && (
              <div className="video-placeholder">
                <Camera size={64} color="#cbd5e1" />
                <p>Camera not active</p>
              </div>
            )}
            <canvas ref={canvasRef} style={{ display: 'none' }} />
          </motion.div>

          {/* OCR Section */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5, delay: 0.2 }}
            className="ocr-section"
          >
            <h3>Text Extraction Controls</h3>

            {/* Input Mode Selection */}
            <div style={{ marginBottom: '20px' }}>
              <label style={{ display: 'block', marginBottom: '10px', fontSize: '14px', fontWeight: '600', color: '#475569' }}>
                Select Input Source:
              </label>
              <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={() => setInputMode('camera')}
                  style={{
                    padding: '10px 16px',
                    borderRadius: '8px',
                    border: '2px solid',
                    borderColor: inputMode === 'camera' ? '#3b82f6' : '#e2e8f0',
                    background: inputMode === 'camera' ? 'linear-gradient(135deg, #3b82f6, #1d4ed8)' : 'white',
                    color: inputMode === 'camera' ? 'white' : '#64748b',
                    cursor: 'pointer',
                    fontSize: '14px',
                    fontWeight: '500',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px'
                  }}
                >
                  <Camera size={18} />
                  Camera
                </motion.button>

                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={() => setInputMode('url')}
                  style={{
                    padding: '10px 16px',
                    borderRadius: '8px',
                    border: '2px solid',
                    borderColor: inputMode === 'url' ? '#3b82f6' : '#e2e8f0',
                    background: inputMode === 'url' ? 'linear-gradient(135deg, #3b82f6, #1d4ed8)' : 'white',
                    color: inputMode === 'url' ? 'white' : '#64748b',
                    cursor: 'pointer',
                    fontSize: '14px',
                    fontWeight: '500',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px'
                  }}
                >
                  <Link size={18} />
                  Image URL
                </motion.button>

                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={() => {
                    setInputMode('pdf');
                    fileInputRef.current?.click();
                  }}
                  style={{
                    padding: '10px 16px',
                    borderRadius: '8px',
                    border: '2px solid',
                    borderColor: inputMode === 'pdf' ? '#3b82f6' : '#e2e8f0',
                    background: inputMode === 'pdf' ? 'linear-gradient(135deg, #3b82f6, #1d4ed8)' : 'white',
                    color: inputMode === 'pdf' ? 'white' : '#64748b',
                    cursor: 'pointer',
                    fontSize: '14px',
                    fontWeight: '500',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px'
                  }}
                >
                  <FileText size={18} />
                  PDF File
                </motion.button>
              </div>
            </div>

            {/* Hidden file input for PDF */}
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,application/pdf"
              onChange={handleFileSelect}
              style={{ display: 'none' }}
            />

            {/* URL Input Section */}
            {inputMode === 'url' && (
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                style={{ marginBottom: '20px' }}
              >
                <label style={{ display: 'block', marginBottom: '8px', fontSize: '14px', color: '#475569' }}>
                  Image URL:
                </label>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <input
                    type="url"
                    value={urlInput}
                    onChange={(e) => setUrlInput(e.target.value)}
                    placeholder="https://example.com/image.jpg"
                    style={{
                      flex: 1,
                      padding: '10px',
                      borderRadius: '8px',
                      border: '1px solid #e2e8f0',
                      fontSize: '14px'
                    }}
                    onKeyPress={(e) => e.key === 'Enter' && handleOCRFromURL()}
                  />
                  <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={handleOCRFromURL}
                    disabled={isProcessingUrl || !urlInput.trim()}
                    style={{
                      padding: '10px 20px',
                      borderRadius: '8px',
                      background: isProcessingUrl || !urlInput.trim()
                        ? '#d1d5db'
                        : 'linear-gradient(135deg, #8b5cf6, #7c3aed)',
                      color: 'white',
                      border: 'none',
                      cursor: isProcessingUrl || !urlInput.trim() ? 'not-allowed' : 'pointer',
                      fontSize: '14px',
                      fontWeight: '500',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px'
                    }}
                  >
                    <Link size={18} />
                    {isProcessingUrl ? 'Processing...' : 'Extract'}
                  </motion.button>
                </div>
                <p style={{ fontSize: '12px', color: '#64748b', marginTop: '5px' }}>
                  Enter a direct link to an image (JPG, PNG, etc.)
                </p>
                <p style={{ fontSize: '11px', color: '#94a3b8', marginTop: '3px', fontStyle: 'italic' }}>
                  Tip: Right-click an image online and select "Copy image address" to get a direct link
                </p>
              </motion.div>
            )}

            {/* PDF Upload Section */}
            {inputMode === 'pdf' && (
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                style={{ marginBottom: '20px' }}
              >
                <label style={{ display: 'block', marginBottom: '8px', fontSize: '14px', color: '#475569' }}>
                  PDF File:
                </label>
                <div
                  onClick={() => fileInputRef.current?.click()}
                  style={{
                    padding: '20px',
                    border: '2px dashed #cbd5e1',
                    borderRadius: '8px',
                    textAlign: 'center',
                    cursor: 'pointer',
                    background: isProcessingPdf ? '#f1f5f9' : '#fafafa',
                    transition: 'all 0.2s'
                  }}
                  onMouseEnter={(e) => !isProcessingPdf && (e.currentTarget.style.borderColor = '#3b82f6')}
                  onMouseLeave={(e) => !isProcessingPdf && (e.currentTarget.style.borderColor = '#cbd5e1')}
                >
                  {isProcessingPdf ? (
                    <div>
                      <div style={{ fontSize: '14px', color: '#64748b' }}>Processing PDF...</div>
                    </div>
                  ) : (
                    <div>
                      <Upload size={32} color="#94a3b8" style={{ marginBottom: '10px' }} />
                      <div style={{ fontSize: '14px', color: '#64748b' }}>
                        {pdfFile ? pdfFile.name : 'Click to upload PDF file'}
                      </div>
                      <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '5px' }}>
                        PDF files will be processed page by page
                      </div>
                    </div>
                  )}
                </div>
              </motion.div>
            )}
            
            {/* Camera Controls - Only show for camera mode */}
            {inputMode === 'camera' && (
              <div className="ocr-controls">
                <button
                  onClick={startCamera}
                  disabled={isStreaming}
                  className="control-button"
                  style={{
                    background: isStreaming 
                      ? '#d1d5db' 
                      : 'linear-gradient(135deg, #3b82f6, #1d4ed8)',
                    color: isStreaming ? '#6b7280' : 'white'
                  }}
                >
                  <Camera size={18} />
                  {isStreaming ? 'Camera Active' : 'Start Camera'}
                </button>

                <button
                  onClick={stopCamera}
                  disabled={!isStreaming}
                  className="control-button"
                  style={{
                    background: !isStreaming 
                      ? '#d1d5db' 
                      : 'linear-gradient(135deg, #ef4444, #dc2626)',
                    color: !isStreaming ? '#6b7280' : 'white'
                  }}
                >
                  <X size={18} />
                  Stop Camera
                </button>
              </div>
            )}

            <div className="ocr-main-actions">
              {/* Extract button - different for each mode */}
              {inputMode === 'camera' && (
                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => handleOCR(false)}
                  disabled={!isStreaming || ocrInProgress}
                  className="ocr-action-button"
                  style={{
                    opacity: (!isStreaming || ocrInProgress) ? 0.5 : 1,
                    cursor: (!isStreaming || ocrInProgress) ? 'not-allowed' : 'pointer'
                  }}
                >
                  <BookOpen size={20} />
                  {ocrInProgress ? 'Extracting Text...' : 'Extract Text from Camera'}
                </motion.button>
              )}

              {inputMode === 'url' && (
                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={handleOCRFromURL}
                  disabled={!urlInput.trim() || isProcessingUrl || ocrInProgress}
                  className="ocr-action-button"
                  style={{
                    opacity: (!urlInput.trim() || isProcessingUrl || ocrInProgress) ? 0.5 : 1,
                    cursor: (!urlInput.trim() || isProcessingUrl || ocrInProgress) ? 'not-allowed' : 'pointer'
                  }}
                >
                  <Link size={20} />
                  {isProcessingUrl || ocrInProgress ? 'Extracting...' : 'Extract Text from URL'}
                </motion.button>
              )}

              {inputMode === 'pdf' && (
                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isProcessingPdf || ocrInProgress}
                  className="ocr-action-button"
                  style={{
                    opacity: (isProcessingPdf || ocrInProgress) ? 0.5 : 1,
                    cursor: (isProcessingPdf || ocrInProgress) ? 'not-allowed' : 'pointer'
                  }}
                >
                  <FileText size={20} />
                  {isProcessingPdf || ocrInProgress ? 'Processing PDF...' : 'Upload & Extract from PDF'}
                </motion.button>
              )}

              {/* Auto-OCR only for camera mode */}
              {inputMode === 'camera' && (
                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={toggleAutoOCR}
                  disabled={!isStreaming}
                  className="ocr-action-button"
                  style={{
                    background: autoOCR 
                      ? 'linear-gradient(135deg, #10b981, #059669)' 
                      : 'linear-gradient(135deg, #6b7280, #4b5563)',
                    opacity: !isStreaming ? 0.5 : 1,
                    cursor: !isStreaming ? 'not-allowed' : 'pointer',
                    marginTop: '10px'
                  }}
                >
                  <RotateCcw size={18} />
                  {autoOCR ? 'Stop Auto-Read' : 'Start Auto-Read (3s)'}
                </motion.button>
              )}
            </div>

            <div className="ocr-lang-select">
              <label htmlFor="ocr-lang">OCR language(s)</label>
              <select
                id="ocr-lang"
                value={ocrLang}
                onChange={(e) => setOcrLang(e.target.value)}
                className="voice-select"
              >
                <option value="en">English</option>
                <option value="hi">Hindi</option>
                <option value="mr">Marathi</option>
                <option value="en,hi">English + Hindi</option>
                <option value="en,mr">English + Marathi</option>
              </select>
              <p className="text-xs text-slate-500 mt-1">Supports up to 3 languages; more languages may slow OCR.</p>
            </div>

            {/* Text Actions */}
            {ocrText && (
              <div className="ocr-text-actions" style={{ 
                display: 'flex', 
                gap: '8px', 
                marginTop: '15px',
                flexWrap: 'wrap'
              }}>
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={speakText}
                  className="control-button"
                  style={{ 
                    background: isSpeaking 
                      ? 'linear-gradient(135deg, #ef4444, #dc2626)' 
                      : 'linear-gradient(135deg, #3b82f6, #1d4ed8)',
                    padding: '8px 12px',
                    fontSize: '14px'
                  }}
                >
                  {isSpeaking ? <Pause size={16} /> : <Play size={16} />}
                  {isSpeaking ? 'Stop Reading' : 'Read Aloud'}
                </motion.button>

                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={copyToClipboard}
                  className="control-button"
                  style={{ 
                    background: 'linear-gradient(135deg, #8b5cf6, #7c3aed)',
                    padding: '8px 12px',
                    fontSize: '14px'
                  }}
                >
                  <Copy size={16} />
                  Copy
                </motion.button>

                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={downloadText}
                  className="control-button"
                  style={{ 
                    background: 'linear-gradient(135deg, #06b6d4, #0891b2)',
                    padding: '8px 12px',
                    fontSize: '14px'
                  }}
                >
                  <Download size={16} />
                  Download
                </motion.button>

                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={clearText}
                  className="control-button"
                  style={{ 
                    background: 'linear-gradient(135deg, #f59e0b, #d97706)',
                    padding: '8px 12px',
                    fontSize: '14px'
                  }}
                >
                  <Trash2 size={16} />
                  Clear
                </motion.button>
              </div>
            )}

            {/* Speech Rate Control */}
            {ocrText && (
              <div style={{ marginTop: '10px', display: 'flex', alignItems: 'center', gap: '10px' }}>
                <label style={{ fontSize: '14px', color: '#64748b' }}>Speech Speed:</label>
                <input
                  type="range"
                  min="0.5"
                  max="2"
                  step="0.1"
                  value={speechRate}
                  onChange={(e) => {
                    setSpeechRate(parseFloat(e.target.value));
                    if (isSpeaking) {
                      window.speechSynthesis.cancel();
                      const utterance = new SpeechSynthesisUtterance(ocrText);
                      utterance.rate = parseFloat(e.target.value);
                      utterance.onend = () => setIsSpeaking(false);
                      window.speechSynthesis.speak(utterance);
                    }
                  }}
                  style={{ flex: 1, maxWidth: '150px' }}
                />
                <span style={{ fontSize: '12px', color: '#64748b', minWidth: '30px' }}>
                  {speechRate.toFixed(1)}x
                </span>
              </div>
            )}

            {/* Results */}
            {ocrText ? (
              <div className="ocr-result-box" style={{ marginTop: '15px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                  <h4 className="font-semibold text-slate-700">Extracted Text:</h4>
                  <span style={{ fontSize: '12px', color: '#64748b' }}>
                    {ocrText.length} characters
                  </span>
                </div>
                <div className="ocr-text-display" style={{ 
                  maxHeight: '300px', 
                  overflowY: 'auto',
                  padding: '12px',
                  background: '#f8fafc',
                  borderRadius: '8px',
                  border: '1px solid #e2e8f0',
                  lineHeight: '1.6',
                  fontSize: '15px'
                }}>
                  {ocrText}
                </div>
              </div>
            ) : (
              <div className="ocr-hint-box" style={{ marginTop: '15px' }}>
                <p>Click "Extract Text from Camera" to read text visible in your camera view.</p>
                <p style={{ marginTop: '8px', fontSize: '13px', color: '#64748b' }}>
                  Or use voice command: "Read text" or "Extract text"
                </p>
              </div>
            )}

            {/* Text History */}
            {textHistory.length > 0 && (
              <div style={{ marginTop: '20px' }}>
                <h4 style={{ fontSize: '14px', fontWeight: '600', color: '#475569', marginBottom: '10px' }}>
                  Recent Extractions ({textHistory.length})
                </h4>
                <div style={{ maxHeight: '150px', overflowY: 'auto' }}>
                  {textHistory.slice(0, 5).map((item, idx) => (
                    <div
                      key={idx}
                      onClick={() => {
                        setOcrText(item.text);
                        speak(`Loaded previous text: ${item.text.substring(0, 50)}...`);
                      }}
                      style={{
                        padding: '8px',
                        marginBottom: '5px',
                        background: '#f1f5f9',
                        borderRadius: '6px',
                        cursor: 'pointer',
                        fontSize: '13px',
                        border: '1px solid #e2e8f0',
                        transition: 'all 0.2s'
                      }}
                      onMouseEnter={(e) => e.target.style.background = '#e2e8f0'}
                      onMouseLeave={(e) => e.target.style.background = '#f1f5f9'}
                    >
                      <div style={{ 
                        color: '#64748b', 
                        fontSize: '11px',
                        marginBottom: '4px'
                      }}>
                        {new Date(item.timestamp).toLocaleTimeString()} - {item.lang}
                      </div>
                      <div style={{ 
                        color: '#334155',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap'
                      }}>
                        {item.text.substring(0, 60)}...
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </motion.div>
        </div>
      </motion.div>
    </div>
  );
};

export default OCRPage;
