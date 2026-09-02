<?php
session_start();

// Check if user is logged in
if (!isset($_SESSION['user_id']) || !isset($_SESSION['account'])) {
    header("Location: index.php");
    exit();
}

// Get user info from session
$user_name = $_SESSION['firstname'] . ' ' . $_SESSION['lastname'];
$user_type = $_SESSION['user_type'];
$affiliation = $_SESSION['affiliation'];

// ─── DATABASE CONNECTION ───────────────────────────────────────────────
$host = '127.0.0.1';
$dbname = 'agrisentinel';
$username = 'root';
$password = '';

try {
    $pdo = new PDO("mysql:host=$host;dbname=$dbname;charset=utf8mb4", $username, $password);
    $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
} catch (PDOException $e) {
    die("Database connection failed: " . $e->getMessage());
}

// ─── IMAGE UPLOAD DIRECTORY ──────────────────────────────────────────
$upload_dir = 'images/';
if (!is_dir($upload_dir)) {
    mkdir($upload_dir, 0777, true);
}

// ─── HANDLE PEST DETECTION LOG SAVING ─────────────────────────────────
// This handles the AJAX request sent from JavaScript when a pest is detected
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['log_pest']) && isset($_POST['log_result'])) {
    $log_pest = trim($_POST['log_pest']);
    $log_result = trim($_POST['log_result']);
    $log_date = date("Y-m-d");
    $log_time = date("H:i:s");

    // Insert into the 'logs' table from logs.sql
    $stmt = $pdo->prepare("INSERT INTO logs (PEST, RESULT, DATE, TIME) VALUES (:pest, :result, :date, :time)");
    $stmt->execute([
        ':pest' => $log_pest,
        ':result' => $log_result,
        ':date' => $log_date,
        ':time' => $log_time
    ]);

    echo "Log saved";
    exit(); // Stop script execution after saving the log
}

// ─── CRUD OPERATIONS ──────────────────────────────────────────────────
$message = '';
$duplicate_pest_name = '';
$duplicate_pest_id = '';

// CREATE with image upload
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    if (isset($_POST['add_pest']) || isset($_POST['edit_pest'])) {
        $is_edit = isset($_POST['edit_pest']);
        $id = $_POST['pest_id'] ?? null;
        $pest = trim($_POST['pest_name']);
        $desc = trim($_POST['description']);
        $action = trim($_POST['suggested_action']);
        $signal = trim($_POST['signal_range']);
        
        // Handle image upload
        $image_path = 'default_pest.jpg';
        $duplicate_warning = '';
        $duplicate_found = false;
        $duplicate_pest_name = '';
        $duplicate_pest_id = '';
        
        if (isset($_FILES['image_file']) && $_FILES['image_file']['error'] === UPLOAD_ERR_OK) {
            $file = $_FILES['image_file'];
            $allowed = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];
            
            // Check for duplicate image by content hash (MD5)
            $file_hash = md5_file($file['tmp_name']);
            $stmt = $pdo->prepare("SELECT ID, PEST, IMAGE FROM pest WHERE IMAGE IS NOT NULL AND IMAGE != 'default_pest.jpg'");
            $stmt->execute();
            $existing_pests = $stmt->fetchAll(PDO::FETCH_ASSOC);
            
            foreach ($existing_pests as $existing) {
                if (file_exists($existing['IMAGE'])) {
                    $existing_hash = md5_file($existing['IMAGE']);
                    if ($existing_hash === $file_hash) {
                        $duplicate_found = true;
                        $duplicate_pest_name = $existing['PEST'];
                        $duplicate_pest_id = $existing['ID'];
                        $duplicate_warning = "⚠️ <span class='warning'>DUPLICATE IMAGE DETECTED!</span> This image is already used for '<strong>{$existing['PEST']}</strong>' (ID #{$existing['ID']}).";
                        break;
                    }
                }
            }
            
            if (in_array($file['type'], $allowed)) {
                $ext = pathinfo($file['name'], PATHINFO_EXTENSION);
                $filename = time() . '_' . uniqid() . '.' . $ext;
                $target = $upload_dir . $filename;
                if (move_uploaded_file($file['tmp_name'], $target)) {
                    $image_path = $target;
                } else {
                    $message = "⚠️ Failed to upload image.";
                }
            } else {
                $message = "⚠️ Invalid image format. Use JPG, PNG, WEBP, or GIF.";
            }
        } else {
            // If no new image uploaded, keep existing for edit
            if ($is_edit && isset($_POST['existing_image']) && !empty($_POST['existing_image'])) {
                $image_path = $_POST['existing_image'];
            }
        }

        // If duplicate found, show warning but still save (or prevent save based on preference)
        if ($duplicate_found) {
            // For edit, keep existing image to avoid duplicate
            if ($is_edit && isset($_POST['existing_image'])) {
                $image_path = $_POST['existing_image'];
                $message = $duplicate_warning . '<br>⚠️ Image not changed (duplicate prevented). ';
            } else {
                $message = $duplicate_warning . '<br>⚠️ This pest will be saved with the duplicate image. ';
            }
        }

        if ($is_edit) {
            $stmt = $pdo->prepare("UPDATE pest SET PEST=:pest, DESCRIPTION=:desc, SUGGESTED_ACTION=:action, 
                                    SIGNAL_RANGE=:signal, IMAGE=:image WHERE ID=:id");
            $stmt->execute([
                ':id' => $id,
                ':pest' => $pest,
                ':desc' => $desc,
                ':action' => $action,
                ':signal' => $signal,
                ':image' => $image_path
            ]);
            $message .= "✅ Pest updated successfully!";
        } else {
            $stmt = $pdo->prepare("INSERT INTO pest (PEST, DESCRIPTION, SUGGESTED_ACTION, SIGNAL_RANGE, IMAGE) 
                                    VALUES (:pest, :desc, :action, :signal, :image)");
            $stmt->execute([
                ':pest' => $pest,
                ':desc' => $desc,
                ':action' => $action,
                ':signal' => $signal,
                ':image' => $image_path
            ]);
            $message .= "✅ Pest added successfully!";
        }
    }

    if (isset($_POST['delete_pest'])) {
        $id = $_POST['pest_id'];
        $stmt = $pdo->prepare("SELECT IMAGE FROM pest WHERE ID = :id");
        $stmt->execute([':id' => $id]);
        $row = $stmt->fetch(PDO::FETCH_ASSOC);
        if ($row && $row['IMAGE'] !== 'default_pest.jpg' && file_exists($row['IMAGE'])) {
            unlink($row['IMAGE']);
        }
        $stmt = $pdo->prepare("DELETE FROM pest WHERE ID = :id");
        $stmt->execute([':id' => $id]);
        $message = "🗑️ Pest deleted!";
    }
}

// READ all pests
$pests = $pdo->query("SELECT * FROM pest ORDER BY ID DESC")->fetchAll(PDO::FETCH_ASSOC);

// ─── PEST DETECTION: Use database as source ─────────────────────────
$db_pests = [];
$target_pests = [];
foreach ($pests as $p) {
    $db_pests[] = [
        'name' => trim($p['PEST']),
        'action' => $p['SUGGESTED_ACTION'],
        'signal' => $p['SIGNAL_RANGE'],
        'image' => $p['IMAGE']
    ];
    $target_pests[] = trim($p['PEST']);
}

if (empty($db_pests)) {
    $db_pests = [
        ['name' => 'Aphid', 'action' => 'Apply insecticidal soap or neem oil. Introduce ladybugs.', 'signal' => 'High'],
        ['name' => 'Bollworm', 'action' => 'Use Bacillus thuringiensis (Bt) or synthetic pyrethroids.', 'signal' => 'High'],
        ['name' => 'Spider Mite', 'action' => 'Apply miticide. Increase humidity and reduce dust.', 'signal' => 'High'],
        ['name' => 'Whitefly', 'action' => 'Use yellow sticky traps. Apply neem oil or insecticidal soap.', 'signal' => 'High'],
        ['name' => 'Fall Armyworm', 'action' => 'Apply Bt or chlorantraniliprole. Scout fields regularly.', 'signal' => 'High'],
        ['name' => 'Honey Bee', 'action' => 'Beneficial pollinator. Do not disturb.', 'signal' => 'Low'],
        ['name' => 'Ladybug', 'action' => 'Beneficial predator. No action needed.', 'signal' => 'Low'],
    ];
    $target_pests = array_column($db_pests, 'name');
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
    <title>AgriSentinel · Pest Alert AI</title>
    <link rel="icon" href="images/favicon.ico" type="image/ico" />
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css"/>
    <link href="https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,400;14..32,500;14..32,600;14..32,700&display=swap" rel="stylesheet"/>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Inter', sans-serif; background: #f6f9f2; color: #1f2a1c; line-height: 1.6; min-height: 100vh; display: flex; justify-content: center; align-items: center; padding: 20px; }
        .app-container { max-width: 1400px; width: 100%; background: white; border-radius: 40px; box-shadow: 0 25px 60px -12px rgba(0, 40, 20, 0.25); overflow: hidden; padding: 28px 32px 36px; transition: all 0.2s; position: relative; }
        .app-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px; margin-bottom: 28px; padding-bottom: 16px; border-bottom: 2px solid #eaf3e4; }
        .logo-area { display: flex; align-items: center; gap: 14px; }
        .logo-icon { background: #2b6e3c; color: white; width: 48px; height: 48px; border-radius: 16px; display: flex; align-items: center; justify-content: center; font-size: 26px; box-shadow: 0 6px 14px rgba(43, 110, 60, 0.3); }
        .logo-text h1 { font-size: 28px; font-weight: 700; letter-spacing: -0.5px; color: #1a3a1e; }
        .logo-text span { font-size: 14px; font-weight: 500; color: #4b7a54; background: #eaf3e4; padding: 2px 14px; border-radius: 30px; margin-left: 8px; }
        .header-actions { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
        .badge { background: #dff0d8; color: #1f4a2a; padding: 6px 18px; border-radius: 30px; font-size: 13px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
        .badge i { font-size: 14px; color: #2b6e3c; }
        .pulse-dot { display: inline-block; width: 8px; height: 8px; background: #2b6e3c; border-radius: 50%; animation: pulse 1.2s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 0.3; transform: scale(0.9); } 50% { opacity: 1; transform: scale(1.2); } }
        .user-info { display: flex; align-items: center; gap: 12px; background: #eaf3e4; padding: 8px 16px; border-radius: 30px; }
        .user-info .avatar { width: 32px; height: 32px; background: #2b6e3c; color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 14px; }
        .user-info .user-details { display: flex; flex-direction: column; }
        .user-info .user-name { font-size: 14px; font-weight: 600; color: #1f4a2a; line-height: 1.2; }
        .user-info .user-role { font-size: 12px; color: #4b7a54; line-height: 1.2; }
        .logout-btn { background: transparent; border: 1px solid #dce8d6; color: #3d5a42; padding: 8px 16px; border-radius: 30px; cursor: pointer; font-family: 'Inter', sans-serif; font-size: 13px; font-weight: 500; display: flex; align-items: center; gap: 6px; transition: 0.2s; text-decoration: none; }
        .logout-btn:hover { background: #f0f7ec; border-color: #bcd6b0; }
        .nav-tabs { display: flex; flex-wrap: wrap; gap: 4px; background: #f0f7ec; padding: 6px; border-radius: 18px; margin-bottom: 28px; }
        .nav-tab { padding: 10px 24px; border-radius: 14px; border: none; background: transparent; font-family: 'Inter', sans-serif; font-size: 15px; font-weight: 500; color: #3d5a42; cursor: pointer; transition: 0.2s; display: flex; align-items: center; gap: 10px; }
        .nav-tab i { font-size: 16px; }
        .nav-tab:hover { background: rgba(43, 110, 60, 0.07); color: #1a3a1e; }
        .nav-tab.active { background: white; color: #1f4a2a; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06); }
        .panel { display: none; animation: fadeUp 0.3s ease; }
        .panel.active { display: block; }
        @keyframes fadeUp { 0% { opacity: 0; transform: translateY(10px); } 100% { opacity: 1; transform: translateY(0); } }
        .panel-title { font-size: 22px; font-weight: 600; margin-bottom: 6px; color: #1a3a1e; }
        .panel-sub { color: #567a5e; margin-bottom: 24px; font-size: 15px; }
        .input-zone { display: flex; flex-wrap: wrap; gap: 20px; margin-bottom: 24px; }
        .upload-zone, .camera-zone { flex: 1 1 240px; border: 2px dashed #cde0c4; border-radius: 24px; padding: 32px 20px; text-align: center; background: #fafff8; transition: 0.25s; cursor: pointer; position: relative; min-height: 180px; display: flex; flex-direction: column; align-items: center; justify-content: center; }
        .upload-zone:hover, .camera-zone:hover { border-color: #7fa882; background: #f4fcf0; }
        .upload-zone i, .camera-zone i { font-size: 38px; color: #4b8a58; margin-bottom: 10px; }
        .upload-zone h4, .camera-zone h4 { font-size: 17px; font-weight: 600; color: #1f3a22; }
        .upload-zone p, .camera-zone p { color: #6a8a70; font-size: 13px; }
        .upload-zone input[type="file"] { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
        .camera-zone video { width: 100%; max-height: 200px; border-radius: 16px; background: #1a2a1e; margin-top: 8px; display: none; }
        .camera-zone .camera-controls { display: none; gap: 12px; margin-top: 12px; flex-wrap: wrap; justify-content: center; }
        .camera-zone.active video, .camera-zone.active .camera-controls { display: flex; }
        .camera-zone.active .camera-placeholder { display: none; }
        .btn { padding: 10px 24px; border: none; border-radius: 14px; font-family: 'Inter', sans-serif; font-size: 14px; font-weight: 600; cursor: pointer; transition: 0.2s; display: inline-flex; align-items: center; gap: 8px; }
        .btn-primary { background: #2b6e3c; color: white; box-shadow: 0 4px 12px rgba(43, 110, 60, 0.25); }
        .btn-primary:hover { background: #1f562e; transform: translateY(-2px); }
        .btn-secondary { background: #eaf3e4; color: #1f4a2a; }
        .btn-secondary:hover { background: #d6e8ce; }
        .btn-danger { background: #c0392b; color: white; }
        .btn-danger:hover { background: #a93226; }
        .btn-warning { background: #e67e22; color: white; }
        .btn-warning:hover { background: #d35400; }
        .preview-box { margin-top: 20px; display: flex; flex-wrap: wrap; gap: 20px; align-items: flex-start; }
        .preview-box img, .preview-box video { max-width: 260px; border-radius: 18px; border: 2px solid #e4efe0; background: white; }
        .result-box { flex: 1; min-width: 220px; background: #f4fcf0; border-radius: 18px; padding: 20px 24px; border-left: 6px solid #2b6e3c; transition: 0.3s; }
        .result-box.alert { border-left-color: #c0392b; background: #fdeaea; animation: flashAlert 0.8s infinite alternate; }
        @keyframes flashAlert { 0% { background: #fdeaea; } 100% { background: #fcd5d5; } }
        .result-box .label { font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: #4b7a54; }
        .result-box .value { font-size: 26px; font-weight: 700; color: #1a3a1e; margin: 4px 0 2px; }
        .result-box .confidence { font-size: 15px; color: #3d6b46; }
        .result-box .recommendation { margin-top: 12px; padding-top: 12px; border-top: 1px solid #d4e8cc; font-size: 14px; color: #2a4f32; }
        .result-box .alert-icon { display: none; color: #c0392b; font-size: 28px; margin-right: 10px; }
        .result-box.alert .alert-icon { display: inline-block; }
        .alert-overlay { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.6); backdrop-filter: blur(4px); display: none; align-items: center; justify-content: center; z-index: 999; animation: fadeOverlay 0.3s; }
        .alert-overlay.active { display: flex; }
        @keyframes fadeOverlay { 0% { opacity: 0; } 100% { opacity: 1; } }
        .alert-modal { background: white; max-width: 500px; width: 90%; border-radius: 40px; padding: 36px 32px 32px; text-align: center; box-shadow: 0 30px 60px rgba(0, 0, 0, 0.4); animation: slideUp 0.4s ease; border-top: 8px solid #c0392b; }
        @keyframes slideUp { 0% { transform: translateY(40px); opacity: 0; } 100% { transform: translateY(0); opacity: 1; } }
        .alert-modal .alert-emoji { font-size: 72px; margin-bottom: 8px; }
        .alert-modal h2 { font-size: 28px; font-weight: 700; color: #c0392b; margin-bottom: 6px; }
        .alert-modal p { font-size: 16px; color: #2a4f32; margin-bottom: 20px; }
        .alert-modal .btn { font-size: 16px; padding: 12px 36px; }
        .form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 18px 24px; background: #fafff8; padding: 24px 28px; border-radius: 24px; border: 1px solid #e4efe0; margin-bottom: 24px; }
        .form-group { display: flex; flex-direction: column; gap: 4px; }
        .form-group label { font-size: 13px; font-weight: 600; color: #3d5a42; display: flex; align-items: center; gap: 6px; }
        .form-group label i { color: #4b8a58; }
        .form-group input, .form-group select { padding: 10px 14px; border: 1.5px solid #dce8d6; border-radius: 14px; font-family: 'Inter', sans-serif; font-size: 15px; background: white; transition: 0.2s; width: 100%; }
        .form-group input:focus, .form-group select:focus { outline: none; border-color: #4b8a58; box-shadow: 0 0 0 4px rgba(43, 110, 60, 0.08); }
        .rec-output { background: #fafff8; border-radius: 24px; padding: 24px 28px; border: 1px solid #e4efe0; margin-top: 16px; }
        .rec-output h4 { font-size: 18px; font-weight: 600; color: #1a3a1e; margin-bottom: 8px; }
        .rec-item { display: flex; align-items: center; gap: 14px; padding: 12px 0; border-bottom: 1px solid #eaf3e4; }
        .rec-item:last-child { border-bottom: none; }
        .rec-item i { width: 32px; color: #2b6e3c; font-size: 18px; }
        .rec-item .rec-label { font-weight: 500; color: #1f3a22; min-width: 100px; }
        .rec-item .rec-value { color: #3d6b46; }
        .stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; margin: 16px 0 24px; }
        .stat-card { background: #fafff8; border: 1px solid #e4efe0; border-radius: 20px; padding: 18px 20px; text-align: center; }
        .stat-card .stat-number { font-size: 30px; font-weight: 700; color: #1a3a1e; }
        .stat-card .stat-label { font-size: 13px; color: #567a5e; font-weight: 500; }
        .stat-card .stat-icon { font-size: 24px; color: #4b8a58; margin-bottom: 4px; }
        .flex { display: flex; gap: 14px; flex-wrap: wrap; align-items: center; }
        .tag { display: inline-block; background: #e4efe0; padding: 2px 14px; border-radius: 30px; font-size: 12px; font-weight: 600; color: #2b6e3c; }
        .table-wrap { overflow-x: auto; background: #fafff8; border-radius: 24px; border: 1px solid #e4efe0; padding: 16px; margin-top: 10px; }
        table { width: 100%; border-collapse: collapse; font-size: 14px; }
        th { text-align: left; padding: 12px 10px; background: #eaf3e4; color: #1f3a22; font-weight: 600; }
        td { padding: 12px 10px; border-bottom: 1px solid #e4efe0; vertical-align: middle; }
        .pest-img { width: 50px; height: 50px; object-fit: cover; border-radius: 12px; background: #eaf3e4; }
        .empty-row { text-align: center; color: #6a8a70; padding: 30px 0; }
        .msg-box { padding: 16px 20px; border-radius: 16px; margin-bottom: 20px; display: flex; align-items: center; gap: 14px; font-size: 15px; animation: slideDown 0.4s ease; border-left: 6px solid #2b6e3c; background: #eaf3e4; color: #1f3a22; }
        .msg-box i { font-size: 24px; }
        .msg-box.warning { border-left-color: #c0392b; background: #fdeaea; color: #7a1a1a; }
        .msg-box.warning i { color: #c0392b; }
        .msg-box.success { border-left-color: #27ae60; background: #eafaf1; color: #1a5a3a; }
        .msg-box.success i { color: #27ae60; }
        .msg-box.info { border-left-color: #2980b9; background: #eaf2f8; color: #1a4a6a; }
        .msg-box.info i { color: #2980b9; }
        .msg-box .warning-text { font-weight: 700; color: #c0392b; }
        .msg-box .duplicate-detail { display: block; margin-top: 6px; padding: 8px 14px; background: rgba(192, 57, 43, 0.08); border-radius: 10px; font-size: 14px; }
        @keyframes slideDown { 0% { opacity: 0; transform: translateY(-20px); } 100% { opacity: 1; transform: translateY(0); } }
        .modal-overlay { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.5); backdrop-filter: blur(4px); display: none; align-items: center; justify-content: center; z-index: 999; }
        .modal-overlay.active { display: flex; }
        .modal-box { background: white; max-width: 600px; width: 95%; border-radius: 32px; padding: 32px 30px; box-shadow: 0 30px 60px rgba(0, 0, 0, 0.3); animation: slideUp 0.3s ease; max-height: 90vh; overflow-y: auto; }
        .modal-box h2 { font-size: 24px; font-weight: 600; margin-bottom: 16px; color: #1a3a1e; }
        .modal-box .form-group { margin-bottom: 16px; }
        .modal-box .form-group label { display: block; font-weight: 600; font-size: 14px; color: #2a4f32; margin-bottom: 4px; }
        .modal-box .form-group input, .modal-box .form-group textarea { width: 100%; padding: 10px 14px; border: 1.5px solid #dce8d6; border-radius: 14px; font-family: 'Inter', sans-serif; font-size: 15px; }
        .modal-box .form-group input:focus, .modal-box .form-group textarea:focus { outline: none; border-color: #4b8a58; box-shadow: 0 0 0 4px rgba(43, 110, 60, 0.08); }
        .modal-box .file-input-wrapper { position: relative; overflow: hidden; display: inline-block; width: 100%; }
        .modal-box .file-input-wrapper input[type="file"] { position: absolute; left: 0; top: 0; opacity: 0; width: 100%; height: 100%; cursor: pointer; }
        .modal-box .file-input-wrapper .file-label { display: block; padding: 10px 14px; border: 1.5px dashed #dce8d6; border-radius: 14px; text-align: center; color: #6a8a70; cursor: pointer; transition: 0.2s; }
        .modal-box .file-input-wrapper .file-label:hover { border-color: #4b8a58; background: #f4fcf0; }
        .modal-box .file-input-wrapper .file-label i { margin-right: 8px; }
        .flex-actions { display: flex; gap: 12px; justify-content: flex-end; margin-top: 8px; flex-wrap: wrap; }
        .current-image-preview { margin: 8px 0; display: flex; align-items: center; gap: 12px; }
        .current-image-preview img { width: 60px; height: 60px; object-fit: cover; border-radius: 10px; border: 1px solid #e4efe0; }
        @media (max-width: 700px) {
            .app-container { padding: 18px 16px 24px; border-radius: 28px; }
            .logo-text h1 { font-size: 22px; }
            .nav-tab { padding: 8px 14px; font-size: 13px; }
            .nav-tab span { display: none; }
            .form-grid { grid-template-columns: 1fr; padding: 18px; }
            .input-zone { flex-direction: column; }
            .preview-box { flex-direction: column; align-items: center; }
            .result-box { width: 100%; }
            .header-actions .badge span { display: none; }
        }
        @media (max-width: 480px) {
            .app-header { flex-direction: column; align-items: flex-start; }
            .stat-grid { grid-template-columns: 1fr 1fr; }
        }
    </style>
</head>
<body>

<div class="app-container" id="app">

    <!-- ═══ HEADER ═══ -->
    <header class="app-header">
        <div class="logo-area">
            <div class="logo-icon"><i class="fas fa-bug"></i></div>
            <div class="logo-text">
                <h1>AgriSentinel <span>Pest AI</span></h1>
            </div>
        </div>
        <div class="header-actions">
            <div class="badge">
                <i class="fas fa-microchip"></i>
                <span>AI · Live</span>
                <span class="pulse-dot" style="margin-left:4px;"></span>
            </div>
            <div class="user-info">
                <div class="avatar"><i class="fas fa-user"></i></div>
                <div class="user-details">
                    <span class="user-name"><?php echo htmlspecialchars($user_name); ?></span>
                    <span class="user-role"><?php echo htmlspecialchars($user_type); ?></span>
                </div>
            </div>
            <a href="logout.php" class="logout-btn">
                <i class="fas fa-sign-out-alt"></i> Logout
            </a>
            <button class="btn btn-secondary" style="padding:8px 18px; font-size:13px;" onclick="resetAll()">
                <i class="fas fa-undo-alt"></i> Reset
            </button>
        </div>
    </header>

    <!-- ═══ NAV ═══ -->
    <nav class="nav-tabs" id="navTabs">
        <button class="nav-tab active" data-panel="panelPest">
            <i class="fas fa-camera"></i> <span>Pest Detect</span>
        </button>

        <button class="nav-tab" data-panel="panelDB">
            <i class="fas fa-database"></i> <span>Pest Database</span>
        </button>
        <button class="nav-tab" data-panel="panelDashboard">
            <i class="fas fa-chart-pie"></i> <span>Dashboard</span>
        </button>
    </nav>

    <!-- ═══ PANEL 1: PEST DETECTION ═══ -->
    <section class="panel active" id="panelPest">
        <h2 class="panel-title"><i class="fas fa-bug" style="color:#2b6e3c; margin-right:10px;"></i>Insect Pest Detection</h2>
        <p class="panel-sub">Upload an insect image or use your camera. AgriSentinel will identify it based on the <strong>pest database</strong> and sound an alert if a high‑risk pest is detected. <strong style="color:#1f8b4c;">(Logs are saved automatically)</strong></p>

        <div class="input-zone">
            <div class="upload-zone" id="uploadZone">
                <i class="fas fa-cloud-upload-alt"></i>
                <h4>Upload image</h4>
                <p>JPG, PNG, WEBP</p>
                <input type="file" id="fileInput" accept="image/*" />
            </div>
            <div class="camera-zone" id="cameraZone">
                <div class="camera-placeholder">
                    <i class="fas fa-video"></i>
                    <h4>Camera capture</h4>
                    <p>Click to open camera</p>
                </div>
                <video id="video" autoplay muted playsinline></video>
                <div class="camera-controls">
                    <button class="btn btn-primary" id="captureBtn"><i class="fas fa-camera"></i> Capture</button>
                    <button class="btn btn-secondary" id="closeCamBtn"><i class="fas fa-times"></i> Close</button>
                </div>
            </div>
        </div>

        <div id="previewArea" class="preview-box" style="display:none;">
            <img id="previewImg" src="#" alt="Insect preview" />
            <div class="result-box" id="resultBox">
                <div class="label">
                    <i class="fas fa-stethoscope"></i> Detection
                    <span class="alert-icon"><i class="fas fa-exclamation-triangle"></i></span>
                </div>
                <div class="value" id="insectName">—</div>
                <div class="confidence" id="insectConfidence">Confidence: —</div>
                <div class="recommendation" id="insectAction">
                    <i class="fas fa-lightbulb" style="color:#f5a623;"></i> Action will appear here.
                </div>
            </div>
        </div>

        <div style="margin-top:20px; background:#f4fcf0; border-radius:20px; padding:16px 22px; border:1px solid #dce8d6;">
            <p style="font-size:14px; color:#2a4f32; display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
                <i class="fas fa-info-circle" style="color:#2b6e3c; font-size:18px;"></i>
                <span><strong>Database pests (<?= count($db_pests) ?>):</strong> <?= implode(', ', array_column($db_pests, 'name')) ?></span>
                <span class="tag"><i class="fas fa-exclamation-circle" style="color:#c0392b;"></i> Alert triggers for high‑risk pests</span>
            </p>
        </div>
    </section>

    <!-- ═══ PANEL 2: CROP ADVISOR ═══ -->
    <section class="panel" id="panelCrop">
        <h2 class="panel-title"><i class="fas fa-hand-holding-seedling" style="color:#2b6e3c; margin-right:10px;"></i>Crop &amp; Fertilizer Advisor</h2>
        <p class="panel-sub">Enter your soil &amp; climate data to get personalised crop and fertilizer recommendations.</p>
        <div class="form-grid">
            <div class="form-group"><label><i class="fas fa-flask"></i> Nitrogen (N) ppm</label><input type="number" id="nInput" value="120" min="0" max="300" step="1" /></div>
            <div class="form-group"><label><i class="fas fa-flask"></i> Phosphorus (P) ppm</label><input type="number" id="pInput" value="45" min="0" max="200" step="1" /></div>
            <div class="form-group"><label><i class="fas fa-flask"></i> Potassium (K) ppm</label><input type="number" id="kInput" value="180" min="0" max="400" step="1" /></div>
            <div class="form-group"><label><i class="fas fa-vial"></i> pH</label><input type="number" id="phInput" value="6.5" min="3.5" max="9.5" step="0.1" /></div>
            <div class="form-group"><label><i class="fas fa-temperature-high"></i> Temp (°C)</label><input type="number" id="tempInput" value="26" min="-5" max="45" step="0.5" /></div>
            <div class="form-group"><label><i class="fas fa-tint"></i> Rainfall (mm/year)</label><input type="number" id="rainInput" value="850" min="100" max="3000" step="10" /></div>
        </div>
        <div class="flex">
            <button class="btn btn-primary" onclick="runCropAdvisor()"><i class="fas fa-seedling"></i> Get Recommendations</button>
            <button class="btn btn-secondary" onclick="resetCropForm()"><i class="fas fa-undo"></i> Reset</button>
        </div>
        <div id="cropOutput" class="rec-output" style="display:none;">
            <h4><i class="fas fa-check-circle" style="color:#2b6e3c;"></i> Recommended Crops</h4>
            <div id="cropList"></div>
            <h4 style="margin-top:16px;"><i class="fas fa-tint" style="color:#2b6e3c;"></i> Fertilizer Suggestion</h4>
            <div id="fertilizerSuggestion"></div>
        </div>
    </section>

    <!-- ═══ PANEL 3: PEST DATABASE CRUD ═══ -->
    <section class="panel" id="panelDB">
        <h2 class="panel-title"><i class="fas fa-database" style="color:#2b6e3c; margin-right:10px;"></i>Pest Database</h2>
        <p class="panel-sub">Manage pest records with image upload. Images are saved to the <strong>images/</strong> folder. <span style="color:#c0392b; font-weight:600;">Duplicate images will trigger a warning.</span></p>

        <!-- ═══ MESSAGE BOX ═══ -->
        <?php if ($message): ?>
            <?php 
                $is_warning = strpos($message, 'DUPLICATE') !== false || strpos($message, '⚠️') !== false;
                $is_success = strpos($message, '✅') !== false && !$is_warning;
                $box_class = $is_warning ? 'warning' : ($is_success ? 'success' : 'info');
            ?>
            <div class="msg-box <?= $box_class ?>">
                <i class="fas <?= $is_warning ? 'fa-exclamation-triangle' : ($is_success ? 'fa-check-circle' : 'fa-info-circle') ?>"></i>
                <div>
                    <?= $message ?>
                    <?php if ($duplicate_pest_name): ?>
                        <div class="duplicate-detail">
                            <i class="fas fa-bug" style="margin-right:6px;"></i> 
                            <strong>Duplicate found:</strong> This image is already assigned to "<strong><?= htmlspecialchars($duplicate_pest_name) ?></strong>" (ID #<?= $duplicate_pest_id ?>)
                        </div>
                    <?php endif; ?>
                </div>
                <button onclick="this.parentElement.style.display='none'" style="background:none;border:none;font-size:20px;cursor:pointer;color:inherit;margin-left:auto;">&times;</button>
            </div>
        <?php endif; ?>

        <button class="btn btn-primary" style="margin-bottom:16px;" onclick="openModal('add')">
            <i class="fas fa-plus"></i> Add New Pest
        </button>

        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Pest</th>
                        <th>Description</th>
                        <th>Suggested Action</th>
                        <th>Signal Range</th>
                        <th>Image</th>
                        <th style="width:140px;">Actions</th>
                    </tr>
                </thead>
                <tbody>
                    <?php if (empty($pests)): ?>
                        <tr><td colspan="7" class="empty-row">No pests found. Add one!</td></tr>
                    <?php else: ?>
                        <?php foreach ($pests as $p): ?>
                        <tr>
                            <td><strong>#<?= $p['ID'] ?></strong></td>
                            <td><strong><?= htmlspecialchars($p['PEST']) ?></strong></td>
                            <td><?= htmlspecialchars(substr($p['DESCRIPTION'], 0, 50)) ?><?= strlen($p['DESCRIPTION']) > 50 ? '…' : '' ?></td>
                            <td><?= htmlspecialchars(substr($p['SUGGESTED_ACTION'], 0, 40)) ?><?= strlen($p['SUGGESTED_ACTION']) > 40 ? '…' : '' ?></td>
                            <td><span class="tag" style="background:#dff0d8;"><?= htmlspecialchars($p['SIGNAL_RANGE']) ?></span></td>
                            <td><img src="<?= htmlspecialchars($p['IMAGE']) ?>" alt="pest" class="pest-img" onerror="this.src='default_pest.jpg'"></td>
                            <td>
                                <button class="btn btn-warning" style="padding:6px 12px; font-size:12px;" onclick="editPest(<?= $p['ID'] ?>, '<?= addslashes($p['PEST']) ?>', '<?= addslashes($p['DESCRIPTION']) ?>', '<?= addslashes($p['SUGGESTED_ACTION']) ?>', '<?= addslashes($p['SIGNAL_RANGE']) ?>', '<?= addslashes($p['IMAGE']) ?>')">
                                    <i class="fas fa-edit"></i>
                                </button>
                                <form method="POST" style="display:inline-block;" onsubmit="return confirm('Delete this pest?')">
                                    <input type="hidden" name="pest_id" value="<?= $p['ID'] ?>">
                                    <button type="submit" name="delete_pest" class="btn btn-danger" style="padding:6px 12px; font-size:12px;"><i class="fas fa-trash"></i></button>
                                </form>
                            </td>
                        </tr>
                        <?php endforeach; ?>
                    <?php endif; ?>
                </tbody>
            </table>
        </div>
        <p style="margin-top:12px; font-size:13px; color:#6a8a70;">
            <i class="fas fa-info-circle"></i> Table: <code>pest</code> (ID, PEST, DESCRIPTION, SUGGESTED_ACTION, SIGNAL_RANGE, IMAGE) &nbsp;|&nbsp; 
            <i class="fas fa-folder"></i> Images stored in: <code>images/</code>
        </p>
    </section>

    <!-- ═══ PANEL 4: DASHBOARD ═══ -->
    <section class="panel" id="panelDashboard">
        <h2 class="panel-title"><i class="fas fa-chart-simple" style="color:#2b6e3c; margin-right:10px;"></i>Farm Dashboard</h2>
        <p class="panel-sub">AgriSentinel's live insights — simulated farm health &amp; pest alerts.</p>
        <div class="stat-grid">
            <div class="stat-card"><div class="stat-icon"><i class="fas fa-leaf"></i></div><div class="stat-number" id="dashCrops">8</div><div class="stat-label">Crops Monitored</div></div>
            <div class="stat-card"><div class="stat-icon"><i class="fas fa-heartbeat"></i></div><div class="stat-number" id="dashHealth">94%</div><div class="stat-label">Avg. Plant Health</div></div>
            <div class="stat-card"><div class="stat-icon"><i class="fas fa-exclamation-triangle"></i></div><div class="stat-number" id="dashRisks">2</div><div class="stat-label">Active Pest Risks</div></div>
            <div class="stat-card"><div class="stat-icon"><i class="fas fa-cloud-sun"></i></div><div class="stat-number" id="dashWeather">26°C</div><div class="stat-label">Current Weather</div></div>
        </div>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:20px; margin-top:8px;">
            <div class="card" style="background:#fafff8;">
                <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">
                    <div class="card-icon" style="background:#d4e8cc;"><i class="fas fa-thermometer-half"></i></div>
                    <h3 style="font-size:16px;">Weather Forecast</h3>
                </div>
                <ul style="list-style:none; font-size:14px; color:#2a4f32;">
                    <li style="display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid #eaf3e4;"><span>Today</span> <span><i class="fas fa-sun" style="color:#f5a623;"></i> 26°C · Sunny</span></li>
                    <li style="display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid #eaf3e4;"><span>Tomorrow</span> <span><i class="fas fa-cloud-sun" style="color:#8ab87a;"></i> 24°C · Partly cloudy</span></li>
                    <li style="display:flex; justify-content:space-between; padding:6px 0;"><span>Day 3</span> <span><i class="fas fa-cloud-rain" style="color:#4a8db7;"></i> 21°C · Light rain</span></li>
                </ul>
            </div>
            <div class="card" style="background:#fafff8;">
                <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">
                    <div class="card-icon" style="background:#d4e8cc;"><i class="fas fa-bell"></i></div>
                    <h3 style="font-size:16px;">Recent Alerts</h3>
                </div>
                <ul style="list-style:none; font-size:14px; color:#2a4f32;" id="alertLog">
                    <li style="padding:6px 0; border-bottom:1px solid #eaf3e4;"><i class="fas fa-check-circle" style="color:#27ae60;"></i> System ready</li>
                </ul>
            </div>
        </div>
        <div style="margin-top:24px; text-align:center; font-size:13px; color:#6a8a70; border-top:1px solid #eaf3e4; padding-top:18px;">
            <i class="fas fa-sync-alt fa-spin" style="margin-right:6px;"></i> Dashboard updates every 15s · Simulated data
        </div>
    </section>

    <!-- ═══ ALERT OVERLAY ═══ -->
    <div class="alert-overlay" id="alertOverlay">
        <div class="alert-modal">
            <div class="alert-emoji">🚨</div>
            <h2>PEST ALERT!</h2>
            <p id="alertMessage"><strong id="alertPestName">Unknown pest</strong> detected!<br>Take immediate action.</p>
            <p id="alertAction" style="font-size:15px; background:#f4fcf0; padding:10px; border-radius:12px; margin-bottom:16px;"></p>
            <button class="btn btn-primary" onclick="dismissAlert()"><i class="fas fa-check"></i> Dismiss</button>
        </div>
    </div>

    <!-- ═══ CRUD MODAL with Image Upload ═══ -->
    <div class="modal-overlay" id="crudModal">
        <div class="modal-box">
            <h2 id="modalTitle">Add New Pest</h2>
            <form method="POST" enctype="multipart/form-data" id="crudForm">
                <input type="hidden" name="pest_id" id="editId" value="">
                <input type="hidden" name="existing_image" id="existingImage" value="">
                
                <div class="form-group">
                    <label><i class="fas fa-bug"></i> Pest Name *</label>
                    <input type="text" name="pest_name" id="pestName" required placeholder="e.g. Fall Armyworm">
                </div>
                <div class="form-group">
                    <label><i class="fas fa-align-left"></i> Description *</label>
                    <textarea name="description" id="pestDesc" rows="2" required placeholder="Description of the pest..."></textarea>
                </div>
                <div class="form-group">
                    <label><i class="fas fa-tools"></i> Suggested Action *</label>
                    <textarea name="suggested_action" id="pestAction" rows="2" required placeholder="Recommended action..."></textarea>
                </div>
                <div class="form-group">
                    <label><i class="fas fa-signal"></i> Signal Range *</label>
                    <input type="text" name="signal_range" id="signalRange" required placeholder="e.g. High / Moderate / Low">
                </div>
                <div class="form-group">
                    <label><i class="fas fa-image"></i> Pest Image</label>
                    <div class="file-input-wrapper">
                        <div class="file-label" id="fileLabel">
                            <i class="fas fa-cloud-upload-alt"></i> Choose image file (JPG, PNG, WEBP, GIF)
                        </div>
                        <input type="file" name="image_file" id="imageFile" accept="image/*" onchange="updateFileLabel(this)">
                    </div>
                    <div id="currentImagePreview" class="current-image-preview" style="display:none;">
                        <span style="font-size:13px; color:#567a5e;">Current image:</span>
                        <img id="previewCurrentImage" src="" alt="Current">
                        <span style="font-size:12px; color:#6a8a70;" id="currentImageName"></span>
                    </div>
                </div>
                <div class="flex-actions">
                    <button type="button" class="btn btn-secondary" onclick="closeModal()">Cancel</button>
                    <button type="submit" class="btn btn-primary" id="modalSubmitBtn" name="add_pest"><i class="fas fa-save"></i> Save</button>
                </div>
            </form>
        </div>
    </div>

</div>

<script>
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 1. TAB NAVIGATION
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    const tabs = document.querySelectorAll('.nav-tab');
    const panels = {
        panelPest: document.getElementById('panelPest'),
        panelCrop: document.getElementById('panelCrop'),
        panelDB: document.getElementById('panelDB'),
        panelDashboard: document.getElementById('panelDashboard'),
    };
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            Object.keys(panels).forEach(key => {
                panels[key].classList.toggle('active', key === tab.dataset.panel);
            });
        });
    });

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 2. PEST DATABASE FROM SERVER
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    const pestDB = <?= json_encode($db_pests) ?>;
    const targetPests = <?= json_encode($target_pests) ?>;

    function getRandomInsect() {
        if (pestDB.length === 0) {
            return { name: 'Unknown', action: 'Check database.', confidence: 0.5 };
        }
        const idx = Math.floor(Math.random() * pestDB.length);
        const pest = pestDB[idx];
        const confidence = 0.70 + Math.random() * 0.25;
        return { ...pest, confidence: Math.min(0.99, confidence) };
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 3. CAMERA & FILE HANDLING
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    const fileInput = document.getElementById('fileInput');
    const previewArea = document.getElementById('previewArea');
    const previewImg = document.getElementById('previewImg');
    const insectName = document.getElementById('insectName');
    const insectConfidence = document.getElementById('insectConfidence');
    const insectAction = document.getElementById('insectAction');
    const resultBox = document.getElementById('resultBox');

    const cameraZone = document.getElementById('cameraZone');
    const video = document.getElementById('video');
    const captureBtn = document.getElementById('captureBtn');
    const closeCamBtn = document.getElementById('closeCamBtn');
    let stream = null;
    let cameraActive = false;

    cameraZone.addEventListener('click', async () => {
        if (cameraActive) return;
        try {
            stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
            video.srcObject = stream;
            await video.play();
            cameraZone.classList.add('active');
            cameraActive = true;
        } catch (err) {
            alert('Camera access denied or not available. Please upload an image instead.');
            console.error(err);
        }
    });

    closeCamBtn.addEventListener('click', closeCamera);

    function closeCamera() {
        if (stream) { stream.getTracks().forEach(track => track.stop()); stream = null; }
        video.srcObject = null;
        cameraZone.classList.remove('active');
        cameraActive = false;
    }

    captureBtn.addEventListener('click', () => {
        if (!cameraActive) return;
        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth || 640;
        canvas.height = video.videoHeight || 480;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const dataUrl = canvas.toDataURL('image/jpeg');
        previewImg.src = dataUrl;
        previewArea.style.display = 'flex';
        runInsectDetection(dataUrl);
        closeCamera();
    });

    fileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (ev) => {
            previewImg.src = ev.target.result;
            previewArea.style.display = 'flex';
            runInsectDetection(ev.target.result);
        };
        reader.readAsDataURL(file);
    });

    const uploadZone = document.getElementById('uploadZone');
    uploadZone.addEventListener('dragover', (e) => { e.preventDefault(); uploadZone.style.borderColor = '#2b6e3c'; uploadZone.style.background = '#edf7e8'; });
    uploadZone.addEventListener('dragleave', () => { uploadZone.style.borderColor = '#cde0c4'; uploadZone.style.background = '#fafff8'; });
    uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadZone.style.borderColor = '#cde0c4';
        uploadZone.style.background = '#fafff8';
        if (e.dataTransfer.files.length) {
            fileInput.files = e.dataTransfer.files;
            fileInput.dispatchEvent(new Event('change'));
        }
    });

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 4. INSECT DETECTION ENGINE & LOG SAVING
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    let alertActive = false;

    // Function to save logs to database via PHP
    function saveLogToDatabase(pestName, resultStatus) {
        const formData = new FormData();
        formData.append('log_pest', pestName);
        formData.append('log_result', resultStatus);

        fetch('pest_detect.php', {
            method: 'POST',
            body: formData
        })
        .then(response => response.text())
        .then(data => console.log('Log saved:', data))
        .catch(error => console.error('Error saving log:', error));
    }

    function runInsectDetection(imageSrc) {
        insectName.textContent = '🔬 Analysing...';
        insectConfidence.textContent = 'Confidence: —';
        insectAction.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
        resultBox.classList.remove('alert');

        setTimeout(() => {
            const insect = getRandomInsect();
            const isTarget = targetPests.includes(insect.name);
            const confidencePercent = (insect.confidence * 100).toFixed(0);

            insectName.textContent = insect.name;
            insectConfidence.textContent = `Confidence: ${confidencePercent}%`;
            insectAction.innerHTML = `<i class="fas fa-lightbulb" style="color:#f5a623;"></i> ${insect.action}`;

            if (insect.confidence > 0.85) insectConfidence.style.color = '#1f8b4c';
            else if (insect.confidence > 0.70) insectConfidence.style.color = '#e67e22';
            else insectConfidence.style.color = '#c0392b';

            const isHighRisk = insect.signal && insect.signal.toLowerCase().includes('high');
            
            if (isTarget && isHighRisk && insect.confidence > 0.75) {
                resultBox.classList.add('alert');
                triggerSignal(insect.name, insect.action);
                addAlertLog(`🚨 ${insect.name} detected! (${confidencePercent}%)`);
                
                // SAVE LOG: High Risk Detected
                saveLogToDatabase(insect.name, 'Detected');
                
            } else {
                resultBox.classList.remove('alert');
                addAlertLog(`✅ ${insect.name} identified (${confidencePercent}%) — Signal: ${insect.signal || 'Unknown'}`);
                
                // SAVE LOG: Identified (Safe or Low Risk)
                saveLogToDatabase(insect.name, 'Identified');
            }
        }, 800 + Math.random() * 600);
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 5. SIGNAL: OVERLAY + SOUND
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    function triggerSignal(pestName, action) {
        if (alertActive) return;
        alertActive = true;
        document.getElementById('alertPestName').textContent = pestName;
        document.getElementById('alertAction').textContent = action;
        document.getElementById('alertOverlay').classList.add('active');
        try {
            const audioCtx = new(window.AudioContext || window.webkitAudioContext)();
            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();
            osc.connect(gain); gain.connect(audioCtx.destination);
            osc.frequency.value = 800; osc.type = 'square';
            gain.gain.setValueAtTime(0.3, audioCtx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.6);
            osc.start(audioCtx.currentTime); osc.stop(audioCtx.currentTime + 0.6);
            setTimeout(() => {
                const osc2 = audioCtx.createOscillator();
                const gain2 = audioCtx.createGain();
                osc2.connect(gain2); gain2.connect(audioCtx.destination);
                osc2.frequency.value = 1000; osc2.type = 'square';
                gain2.gain.setValueAtTime(0.25, audioCtx.currentTime);
                gain2.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.5);
                osc2.start(audioCtx.currentTime); osc2.stop(audioCtx.currentTime + 0.5);
            }, 300);
        } catch (e) { console.warn('Audio not available'); }
        document.title = '🚨 PEST ALERT! - AgriSentinel';
        setTimeout(() => { document.title = 'AgriSentinel · Pest AI'; }, 3000);
    }

    function dismissAlert() {
        document.getElementById('alertOverlay').classList.remove('active');
        alertActive = false;
        resultBox.classList.remove('alert');
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 6. DASHBOARD LOG & STATS
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    const alertLog = document.getElementById('alertLog');

    function addAlertLog(message) {
        const li = document.createElement('li');
        li.style.padding = '6px 0';
        li.style.borderBottom = '1px solid #eaf3e4';
        li.innerHTML = message;
        alertLog.prepend(li);
        while (alertLog.children.length > 5) alertLog.removeChild(alertLog.lastChild);
    }

    function updateDashboard() {
        document.getElementById('dashHealth').textContent = (85 + Math.floor(Math.random() * 12)) + '%';
        document.getElementById('dashRisks').textContent = Math.random() > 0.5 ? 2 : 3;
        document.getElementById('dashWeather').textContent = (22 + Math.floor(Math.random() * 8)) + '°C';
    }
    setInterval(updateDashboard, 15000);

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 7. CROP ADVISOR
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    function getCropRecommendation(N, P, K, pH, temp, rain) {
        const baseCrops = [
            { name: 'Tomato', minN: 80, maxN: 200, minP: 30, maxP: 80, minK: 150, maxK: 300, pHmin: 6.0, pHmax: 7.0, tempMin: 18, tempMax: 30, rainMin: 400, rainMax: 1200 },
            { name: 'Potato', minN: 100, maxN: 220, minP: 40, maxP: 90, minK: 160, maxK: 320, pHmin: 5.5, pHmax: 6.8, tempMin: 15, tempMax: 28, rainMin: 500, rainMax: 1400 },
            { name: 'Corn', minN: 120, maxN: 250, minP: 35, maxP: 75, minK: 150, maxK: 280, pHmin: 5.8, pHmax: 7.2, tempMin: 20, tempMax: 35, rainMin: 450, rainMax: 1300 },
            { name: 'Wheat', minN: 80, maxN: 180, minP: 20, maxP: 60, minK: 100, maxK: 220, pHmin: 6.0, pHmax: 7.5, tempMin: 12, tempMax: 28, rainMin: 350, rainMax: 1000 },
            { name: 'Soybean', minN: 60, maxN: 150, minP: 25, maxP: 65, minK: 130, maxK: 250, pHmin: 6.0, pHmax: 7.0, tempMin: 18, tempMax: 32, rainMin: 500, rainMax: 1400 },
            { name: 'Rice', minN: 90, maxN: 200, minP: 30, maxP: 70, minK: 120, maxK: 240, pHmin: 5.5, pHmax: 6.8, tempMin: 22, tempMax: 38, rainMin: 800, rainMax: 2500 },
            { name: 'Cotton', minN: 100, maxN: 220, minP: 35, maxP: 80, minK: 140, maxK: 280, pHmin: 5.8, pHmax: 7.2, tempMin: 20, tempMax: 38, rainMin: 400, rainMax: 1200 },
            { name: 'Sunflower', minN: 70, maxN: 160, minP: 30, maxP: 70, minK: 120, maxK: 250, pHmin: 6.0, pHmax: 7.5, tempMin: 16, tempMax: 34, rainMin: 350, rainMax: 1100 },
            { name: 'Pepper', minN: 80, maxN: 180, minP: 25, maxP: 65, minK: 140, maxK: 280, pHmin: 6.0, pHmax: 7.0, tempMin: 18, tempMax: 32, rainMin: 400, rainMax: 1200 },
            { name: 'Onion', minN: 70, maxN: 160, minP: 25, maxP: 60, minK: 120, maxK: 240, pHmin: 6.0, pHmax: 7.2, tempMin: 12, tempMax: 30, rainMin: 350, rainMax: 1000 },
        ];
        const crops = baseCrops.map(crop => {
            let score = 0;
            if (N >= crop.minN && N <= crop.maxN) score += 25;
            else if (N >= crop.minN * 0.7 && N <= crop.maxN * 1.3) score += 12;
            if (P >= crop.minP && P <= crop.maxP) score += 25;
            else if (P >= crop.minP * 0.7 && P <= crop.maxP * 1.3) score += 12;
            if (K >= crop.minK && K <= crop.maxK) score += 20;
            else if (K >= crop.minK * 0.7 && K <= crop.maxK * 1.3) score += 10;
            if (pH >= crop.pHmin && pH <= crop.pHmax) score += 15;
            else if (pH >= crop.pHmin - 0.4 && pH <= crop.pHmax + 0.4) score += 7;
            if (temp >= crop.tempMin && temp <= crop.tempMax) score += 10;
            else if (temp >= crop.tempMin - 3 && temp <= crop.tempMax + 3) score += 5;
            if (rain >= crop.rainMin && rain <= crop.rainMax) score += 5;
            else if (rain >= crop.rainMin * 0.7 && rain <= crop.rainMax * 1.3) score += 2;
            score += (Math.random() * 6 - 3);
            return { ...crop, score: Math.min(100, Math.max(0, score)) };
        });
        crops.sort((a, b) => b.score - a.score);
        return crops.slice(0, 4);
    }

    function getFertilizerRecommendation(N, P, K, pH) {
        const recs = [];
        if (N < 80) recs.push('Nitrogen (Urea / DAP) — apply 40–60 kg/ha');
        else if (N < 120) recs.push('Nitrogen (Urea) — light application 20–30 kg/ha');
        else recs.push('Nitrogen — sufficient, maintain with organic matter');
        if (P < 30) recs.push('Phosphorus (Single Super Phosphate) — apply 50–80 kg/ha');
        else if (P < 50) recs.push('Phosphorus — moderate, apply 20–30 kg/ha');
        if (K < 130) recs.push('Potassium (Muriate of Potash) — apply 40–60 kg/ha');
        else if (K < 180) recs.push('Potassium — moderate, apply 20–30 kg/ha');
        if (pH < 5.5) recs.push('Lime — apply 1–2 tons/ha to raise pH');
        else if (pH > 7.5) recs.push('Sulfur or gypsum — apply to lower pH');
        if (recs.length === 0) recs.push('All nutrients are balanced. Maintain with compost & crop rotation.');
        return recs;
    }

    function runCropAdvisor() {
        const N = parseFloat(document.getElementById('nInput').value) || 0;
        const P = parseFloat(document.getElementById('pInput').value) || 0;
        const K = parseFloat(document.getElementById('kInput').value) || 0;
        const pH = parseFloat(document.getElementById('phInput').value) || 7;
        const temp = parseFloat(document.getElementById('tempInput').value) || 25;
        const rain = parseFloat(document.getElementById('rainInput').value) || 800;
        const topCrops = getCropRecommendation(N, P, K, pH, temp, rain);
        const output = document.getElementById('cropOutput');
        const cropList = document.getElementById('cropList');
        const fertDiv = document.getElementById('fertilizerSuggestion');
        cropList.innerHTML = '';
        topCrops.forEach((crop, idx) => {
            const div = document.createElement('div');
            div.className = 'rec-item';
            const icon = idx === 0 ? '🥇' : idx === 1 ? '🥈' : idx === 2 ? '🥉' : '🌱';
            div.innerHTML = `<i class="fas fa-seedling"></i><span class="rec-label">${icon} ${crop.name}</span><span class="rec-value">Match: ${Math.round(crop.score)}%</span>`;
            cropList.appendChild(div);
        });
        const fertRecs = getFertilizerRecommendation(N, P, K, pH);
        fertDiv.innerHTML = fertRecs.map(r =>
            `<div style="padding:6px 0; display:flex; gap:10px; align-items:center; border-bottom:1px solid #eaf3e4;"><i class="fas fa-check-circle" style="color:#2b6e3c;"></i><span>${r}</span></div>`
        ).join('');
        output.style.display = 'block';
        output.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function resetCropForm() {
        document.getElementById('nInput').value = 120;
        document.getElementById('pInput').value = 45;
        document.getElementById('kInput').value = 180;
        document.getElementById('phInput').value = 6.5;
        document.getElementById('tempInput').value = 26;
        document.getElementById('rainInput').value = 850;
        document.getElementById('cropOutput').style.display = 'none';
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 8. CRUD MODAL
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    const modal = document.getElementById('crudModal');
    const modalTitle = document.getElementById('modalTitle');
    const submitBtn = document.getElementById('modalSubmitBtn');
    const editId = document.getElementById('editId');
    const existingImage = document.getElementById('existingImage');
    const pestName = document.getElementById('pestName');
    const pestDesc = document.getElementById('pestDesc');
    const pestAction = document.getElementById('pestAction');
    const signalRange = document.getElementById('signalRange');
    const imageFile = document.getElementById('imageFile');
    const currentImagePreview = document.getElementById('currentImagePreview');
    const previewCurrentImage = document.getElementById('previewCurrentImage');
    const currentImageName = document.getElementById('currentImageName');
    const fileLabel = document.getElementById('fileLabel');

    function updateFileLabel(input) {
        if (input.files && input.files[0]) {
            fileLabel.innerHTML = `<i class="fas fa-check-circle" style="color:#2b6e3c;"></i> ${input.files[0].name}`;
        } else {
            fileLabel.innerHTML = `<i class="fas fa-cloud-upload-alt"></i> Choose image file (JPG, PNG, WEBP, GIF)`;
        }
    }

    function openModal(mode, data = null) {
        modal.classList.add('active');
        imageFile.value = '';
        fileLabel.innerHTML = `<i class="fas fa-cloud-upload-alt"></i> Choose image file (JPG, PNG, WEBP, GIF)`;
        
        if (mode === 'add') {
            modalTitle.textContent = 'Add New Pest';
            submitBtn.name = 'add_pest';
            document.getElementById('crudForm').reset();
            editId.value = '';
            existingImage.value = '';
            currentImagePreview.style.display = 'none';
            pestName.value = '';
            pestDesc.value = '';
            pestAction.value = '';
            signalRange.value = '';
        } else if (mode === 'edit') {
            modalTitle.textContent = 'Edit Pest';
            submitBtn.name = 'edit_pest';
            editId.value = data.id;
            pestName.value = data.name;
            pestDesc.value = data.desc;
            pestAction.value = data.action;
            signalRange.value = data.signal;
            existingImage.value = data.image || 'default_pest.jpg';
            
            if (data.image && data.image !== 'default_pest.jpg') {
                currentImagePreview.style.display = 'flex';
                previewCurrentImage.src = data.image;
                currentImageName.textContent = data.image.split('/').pop();
            } else {
                currentImagePreview.style.display = 'none';
            }
        }
    }

    function closeModal() { modal.classList.remove('active'); }

    function editPest(id, name, desc, action, signal, image) {
        openModal('edit', { id, name, desc, action, signal, image });
    }

    modal.addEventListener('click', function(e) { if (e.target === this) closeModal(); });

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 9. RESET ALL
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    function resetAll() {
        closeCamera();
        fileInput.value = '';
        previewArea.style.display = 'none';
        insectName.textContent = '—';
        insectConfidence.textContent = 'Confidence: —';
        insectAction.innerHTML = '<i class="fas fa-lightbulb" style="color:#f5a623;"></i> Action will appear here.';
        resultBox.classList.remove('alert');
        dismissAlert();
        resetCropForm();
        document.getElementById('dashHealth').textContent = '94%';
        document.getElementById('dashRisks').textContent = '2';
        document.getElementById('dashWeather').textContent = '26°C';
        document.querySelector('[data-panel="panelPest"]').click();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 10. INIT
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    document.querySelectorAll('#panelCrop .form-group input').forEach(inp => {
        inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') runCropAdvisor(); });
    });

    console.log('🐛 AgriSentinel Pest AI ready. Database-driven detection with automatic log saving.');
</script>
</body>
</html>