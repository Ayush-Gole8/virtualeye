import React, { useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import { useDropzone } from 'react-dropzone';
import { Upload, Image as ImageIcon, AlertCircle, CheckCircle, X } from 'lucide-react';
import axios from 'axios';
import './Demo.css';

const ImageUploadComponent = ({ apiUrl, lang, onAnalysisComplete, onError, onStartLoading, isLoading, onPlayAudio }) => {
  const [uploadedImage, setUploadedImage] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [error, setError] = useState(null);
  const [showPreview, setShowPreview] = useState(true);

  const onDrop = useCallback((acceptedFiles, rejectedFiles) => {
    setError(null);
    
    if (rejectedFiles.length > 0) {
      setError('Please upload a valid image file (JPG, PNG, JPEG)');
      return;
    }

    const file = acceptedFiles[0];
    if (file) {
      setUploadedImage(file);
      const url = URL.createObjectURL(file);
      setPreviewUrl(url);
      setShowPreview(true);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'image/*': ['.jpeg', '.jpg', '.png']
    },
    maxFiles: 1,
    maxSize: 10 * 1024 * 1024 // 10MB
  });

  const removeImage = () => {
    setUploadedImage(null);
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      setPreviewUrl(null);
    }
    setError(null);
    setShowPreview(true);
  };

  const analyzeImage = async () => {
    if (!uploadedImage) {
      setError('Please upload an image first');
      return;
    }

    try {
      onStartLoading();
      setError(null);

      const formData = new FormData();
      formData.append('frame', uploadedImage);
      formData.append('lang', lang || 'en');

      const response = await axios.post(`${apiUrl}/analyze_frame`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        timeout: 30000
      });

      if (response.data) {
        // Hide preview and show analysis results
        setShowPreview(false);
        const resultsData = {
          description: response.data.caption_translated || response.data.caption,
          detections: response.data.detections || [],
          annotatedImage: response.data.annotated_image ? `data:image/png;base64,${response.data.annotated_image}` : null,
          originalImage: previewUrl,
          ttsAudio: response.data.tts_audio // Store audio but don't play it automatically
        };
        onAnalysisComplete(resultsData);
      }

    } catch (err) {
      console.error('Analysis error:', err);
      const errorMessage = err.response?.data?.error || err.message || 'Analysis failed. Please try again.';
      setError(errorMessage);
      onError(new Error(errorMessage));
    }
  };

  return (
    <div className="upload-component">
      <div className="upload-header">
        <h2>Upload Image for Analysis</h2>
        <p>Drag and drop an image or click to browse files</p>
      </div>

      <div className="upload-content">
        {!uploadedImage ? (
          <div
            {...getRootProps()}
            className={`dropzone ${isDragActive ? 'active' : ''}`}
          >
            <input {...getInputProps()} />
            <div className="dropzone-content">
              <motion.div
                animate={{ scale: isDragActive ? 1.1 : 1 }}
                transition={{ duration: 0.2 }}
              >
                <Upload className="dropzone-icon" />
              </motion.div>
              <h3>
                {isDragActive ? 'Drop the image here' : 'Choose an image to analyze'}
              </h3>
              <p>Supports JPG, PNG, JPEG files up to 10MB</p>
              <div className="supported-formats">
                <span className="format-tag">JPG</span>
                <span className="format-tag">PNG</span>
                <span className="format-tag">JPEG</span>
              </div>
            </div>
          </div>
        ) : (
          <div className="image-preview-section">
            <div className="preview-header">
              <h3>Image Preview</h3>
              <button onClick={removeImage} className="remove-button">
                <X className="remove-icon" />
              </button>
            </div>
            
            {showPreview && (
              <div className="image-preview">
                <img src={previewUrl} alt="Uploaded" className="preview-image" />
              </div>
            )}

            <div className="image-info">
              <div className="info-item">
                <ImageIcon className="info-icon" />
                <span>{uploadedImage.name}</span>
              </div>
              <div className="info-item">
                <CheckCircle className="info-icon success" />
                <span>{(uploadedImage.size / 1024 / 1024).toFixed(2)} MB</span>
              </div>
            </div>

            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={analyzeImage}
              className="analyze-button"
              disabled={isLoading}
            >
              {isLoading ? 'Analyzing...' : 'Analyze Image'}
            </motion.button>
          </div>
        )}

        {error && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="error-message"
          >
            <AlertCircle className="error-icon" />
            <span>{error}</span>
          </motion.div>
        )}

        {uploadedImage && (
          <div className="upload-tips">
            <h4>Tips for better analysis:</h4>
            <ul>
              <li>Use clear, well-lit images</li>
              <li>Ensure objects are clearly visible</li>
              <li>Higher resolution images work better</li>
              <li>Avoid blurry or dark photos</li>
            </ul>
          </div>
        )}
      </div>
    </div>
  );
};

export default ImageUploadComponent;
