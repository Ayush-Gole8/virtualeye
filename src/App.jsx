import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { VoiceProvider } from './context/VoiceNavigationContext';

// Pages
import LandingPage from './pages/LandingPage';
import DashboardLayout from './components/layout/DashboardLayout';
import DashboardHome from './pages/DashboardHome';
import VisionPage from './pages/VisionPage';
import OCRPage from './pages/OCRPage';
import Demo from './pages/Demo';

// Styles
import './App.css';
function AppContent() {
  return (
    <>
      <Toaster position="top-center" toastOptions={{
        style: { background: '#1e293b', color: '#fff' }
      }}/>
      
      <Routes>
        {/* Public Route */}
        <Route path="/" element={<LandingPage />} />

        {/* Protected Dashboard Routes */}
        <Route path="/dashboard" element={<DashboardLayout />}>
          <Route index element={<DashboardHome />} />
          <Route path="vision" element={<VisionPage />} />
          <Route path="ocr" element={<OCRPage />} />
          <Route path="demopurpose" element={<Demo />} />
          
          {/* Add these later */}
          <Route path="settings" element={<div className="p-10">Settings Coming Soon</div>} />
        </Route>
      </Routes>
    </>
  );
}

function App() {
  return (
    <Router>
      <VoiceProvider>
        <AppContent />
      </VoiceProvider>
    </Router>
  );
}

export default App;