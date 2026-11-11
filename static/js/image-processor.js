/**
 * Image Processing Utility for Barcode Scanner
 * Mengonversi gambar kamera ke Grayscale dan mengoptimalkan kontras
 * agar garis-garis barcode terlihat tajam dan mudah dibaca
 */

var ImageProcessor = (function() {
    'use strict';
    
    var _canvas = null;
    var _ctx = null;
    var _grayCanvas = null;
    var _grayCtx = null;
    var _imageData = null;
    
    /**
     * Inisialisasi canvas untuk pemrosesan gambar
     */
    function _initCanvas(width, height) {
        if (!_canvas || _canvas.width !== width || _canvas.height !== height) {
            _canvas = document.createElement('canvas');
            _canvas.width = width;
            _canvas.height = height;
            _ctx = _canvas.getContext('2d', { willReadFrequently: true });
            
            _grayCanvas = document.createElement('canvas');
            _grayCanvas.width = width;
            _grayCanvas.height = height;
            _grayCtx = _grayCanvas.getContext('2d', { willReadFrequently: true });
        }
    }
    
    /**
     * Konversi RGB ke Grayscale menggunakan formula luminansi
     * Y = 0.299*R + 0.587*G + 0.114*B ( человеческое mata/mesin)
     * Untuk barcode: menggunakan weighted formula yang lebih baik untuk kontras
     */
    function _toGrayscale(imageData) {
        var data = imageData.data;
        var len = data.length;
        var gray = new Uint8ClampedArray(len);
        
        for (var i = 0; i < len; i += 4) {
            // Gunakan weighted formula untuk readability barcode
            // Merah lebih penting untuk barcode hitam-merah
            var r = data[i];
            var g = data[i + 1];
            var b = data[i + 2];
            
            // Formula luminansi yang dioptimalkan untuk barcode
            // Menggunakan higher weight untuk green karena sensor mobile
            // lebih sensitive terhadap hijau
            var y = Math.round(0.299 * r + 0.587 * g + 0.114 * b);
            
            data[i] = y;     // R
            data[i + 1] = y; // G
            data[i + 2] = y; // B
            // Alpha tetap sama
        }
        
        return imageData;
    }
    
    /**
     * Optimasi kontras menggunakan CLAHE (Contrast Limited Adaptive Histogram Equalization)
     * yang lebih baik untuk barcode daripada histogram equalization biasa
     */
    function _optimizeContrast(imageData, clipLimit) {
        clipLimit = clipLimit || 2.0;
        var data = imageData.data;
        var width = imageData.width;
        var height = imageData.height;
        
        // Untuk kecepatan, gunakan pendekatan sederhana:
        // Contrast stretching dengan linear mapping
        
        // Hitung min dan max
        var min = 255, max = 0;
        for (var i = 0; i < data.length; i += 4) {
            var val = data[i]; // Karena sudah grayscale, R=G=B
            if (val < min) min = val;
            if (val > max) max = val;
        }
        
        // Avoid division by zero
        if (max === min) return imageData;
        
        // Kontras stretching: rentang 0-255
        var range = max - min;
        var factor = 255 / range;
        
        for (var i = 0; i < data.length; i += 4) {
            var val = data[i];
            var newVal = Math.round((val - min) * factor);
            
            // Sigmoid stretching untuk kontras lebih tajam
            // Ini membuat garis barcode lebih gelap dan background lebih terang
            newVal = Math.round(255 / (1 + Math.exp(-0.05 * (newVal - 128))));
            
            data[i] = newVal;
            data[i + 1] = newVal;
            data[i + 2] = newVal;
        }
        
        return imageData;
    }
    
    /**
     * Sharpening filter menggunakan convolution matrix
     * Membuat tepi garis barcode lebih tajam
     */
    function _sharpen(imageData) {
        var width = imageData.width;
        var height = imageData.height;
        var data = imageData.data;
        
        // Buat salinan untuk reading
        var src = new Uint8ClampedArray(data);
        
        // Sharpening kernel yang lebih kuat untuk barcode
        // [ 0 -1  0 ]
        // [-1  5 -1 ]
        // [ 0 -1  0 ]
        
        for (var y = 1; y < height - 1; y++) {
            for (var x = 1; x < width - 1; x++) {
                var idx = (y * width + x) * 4;
                
                var center = src[idx];
                var top = src[((y - 1) * width + x) * 4];
                var bottom = src[((y + 1) * width + x) * 4];
                var left = src[(y * width + (x - 1)) * 4];
                var right = src[(y * width + (x + 1)) * 4];
                
                // Apply sharpening convolution
                var result = 5 * center - top - bottom - left - right;
                
                // Clamp ke nilai yang valid
                result = Math.max(0, Math.min(255, result));
                
                data[idx] = result;
                data[idx + 1] = result;
                data[idx + 2] = result;
            }
        }
        
        return imageData;
    }
    
    /**
     * Binarization dengan threshold adaptif untuk barcode
     * Menghasilkan gambar hitam-putih murni
     */
    function _binarize(imageData, threshold) {
        threshold = threshold || 128;
        
        var data = imageData.data;
        var len = data.length;
        
        for (var i = 0; i < len; i += 4) {
            var val = data[i]; // Grayscale value
            
            // Otsu's method-inspired thresholding
            var binary = val > threshold ? 255 : 0;
            
            data[i] = binary;
            data[i + 1] = binary;
            data[i + 2] = binary;
        }
        
        return imageData;
    }
    
    /**
     * Adaptive thresholding - lebih baik untuk kondisi pencahayaan tidak merata
     */
    function _adaptiveThreshold(imageData, blockSize, C) {
        blockSize = blockSize || 11;
        C = C || 2;
        
        var width = imageData.width;
        var height = imageData.height;
        var data = imageData.data;
        var src = new Uint8ClampedArray(data);
        
        // Hitung local mean untuk setiap pixel
        for (var y = 0; y < height; y++) {
            for (var x = 0; x < width; x++) {
                var idx = (y * width + x) * 4;
                
                // Hitung mean dalam block
                var sum = 0;
                var count = 0;
                
                var half = Math.floor(blockSize / 2);
                for (var by = -half; by <= half; by++) {
                    for (var bx = -half; bx <= half; bx++) {
                        var ny = y + by;
                        var nx = x + bx;
                        
                        if (ny >= 0 && ny < height && nx >= 0 && nx < width) {
                            sum += src[(ny * width + nx) * 4];
                            count++;
                        }
                    }
                }
                
                var localMean = sum / count;
                var pixelVal = src[idx];
                var threshold = localMean - C;
                
                var binary = pixelVal > threshold ? 255 : 0;
                
                data[idx] = binary;
                data[idx + 1] = binary;
                data[idx + 2] = binary;
            }
        }
        
        return imageData;
    }
    
    /**
     * Proses utama: Konversi ke grayscale + optimize contrast + sharpen
     * Ini adalah fungsi yang應該 dipanggil sebelum scanner memproses frame
     */
    function processFrame(videoElement, options) {
        options = options || {};
        
        var width = options.width || videoElement.videoWidth || 640;
        var height = options.height || videoElement.videoHeight || 480;
        
        // Inisialisasi canvas jika perlu
        _initCanvas(width, height);
        
        // Gambar video ke canvas
        _ctx.drawImage(videoElement, 0, 0, width, height);
        
        // Ambil data gambar
        _imageData = _ctx.getImageData(0, 0, width, height);
        
        // Step 1: Konversi ke Grayscale
        _imageData = _toGrayscale(_imageData);
        
        // Step 2: Optimasi kontras
        if (options.optimizeContrast !== false) {
            _imageData = _optimizeContrast(_imageData);
        }
        
        // Step 3: Sharpening (opsional, tapi sangat membantu untuk barcode)
        if (options.sharpen !== false) {
            _imageData = _sharpen(_imageData);
        }
        
        // Step 4: Binarization (opsional - menghasilkan gambar hitam-putih murni)
        // Ini sangat membantu untuk barcode 1D
        if (options.binarize) {
            if (options.adaptiveThreshold) {
                _imageData = _adaptiveThreshold(_imageData);
            } else {
                _imageData = _binarize(_imageData, options.threshold || 128);
            }
        }
        
        // Simpan ke grayscale canvas dan return
        _grayCtx.putImageData(_imageData, 0, 0);
        
        return _grayCanvas;
    }
    
    /**
     * Proses frame dan return ImageData untuk scanner
     * Gunakan ini jika scanner membutuhkan ImageData
     */
    function processToImageData(videoElement, options) {
        options = options || {};
        
        var width = options.width || videoElement.videoWidth || 640;
        var height = options.height || videoElement.videoHeight || 480;
        
        _initCanvas(width, height);
        
        _ctx.drawImage(videoElement, 0, 0, width, height);
        _imageData = _ctx.getImageData(0, 0, width, height);
        
        // Proses lengkap untuk barcode
        _imageData = _toGrayscale(_imageData);
        _imageData = _optimizeContrast(_imageData);
        _imageData = _sharpen(_imageData);
        
        if (options.binarize) {
            _imageData = _binarize(_imageData, options.threshold);
        }
        
        return _imageData;
    }
    
    /**
     * Dapatkan canvas grayscale untuk ditampilkan (debugging)
     */
    function getGrayscaleCanvas() {
        return _grayCanvas;
    }
    
    /**
     * Reset/cleanup
     */
    function reset() {
        _canvas = null;
        _ctx = null;
        _grayCanvas = null;
        _grayCtx = null;
        _imageData = null;
    }
    
    // Public API
    return {
        processFrame: processFrame,
        processToImageData: processToImageData,
        getGrayscaleCanvas: getGrayscaleCanvas,
        toGrayscale: function(imgData) { return _toGrayscale(imgData); },
        optimizeContrast: function(imgData) { return _optimizeContrast(imgData); },
        sharpen: function(imgData) { return _sharpen(imgData); },
        binarize: function(imgData, threshold) { return _binarize(imgData, threshold); },
        adaptiveThreshold: function(imgData) { return _adaptiveThreshold(imgData); },
        reset: reset
    };
})();

// Export untuk penggunaan global
if (typeof window !== 'undefined') {
    window.ImageProcessor = ImageProcessor;
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = ImageProcessor;
}
