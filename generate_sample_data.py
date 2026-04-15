#!/usr/bin/env python3
"""
Generate sample list.map.post file for testing the CPU CHECK monitor
Format: field1 ... username.lastname PID_group
"""
import random
import os

# Sample data matching the screenshot
users = [
    ("chanh.tran", "PID1"), ("anhtuan.pham", "PID1"), ("vinhkhang.tran", "PID1"),
    ("nguyenkhang.tran", "PID1"), ("tuan.pham", "PID1"), ("tien.nguyen", "PID1"),
    ("dang.nguyen", "PID1"), ("du.van", "PID1"), ("ductoan.nguyen", "PID1"),
    ("loc.ngo", "PID1"), ("huy.ho", "PID1"), ("nhan.pham", "PID1"),
    ("long.nguyen", "PID1"), ("vinh.lam", "PID3"), ("phat.nguyen", "PID3"),
    ("thinh.pham", "PID3"), ("hai.le", "PID3"), ("nhantai.nguyen", "PID3"),
    ("dat.do", "PID3"), ("ty.truongvan", "PID3"), ("vinh.dinhngo", "PID3"),
    ("long.baonguyen", "PID1"), ("thanh.nguyenchi", "PID1"), ("anh.pham", "PID1"),
    ("thuc.pham", "PID1"), ("chuan.le", "EO"), ("minh.cao", "PID3"),
    ("tan.huynh", "AC"), ("lpk.minh", "PID1"), ("tri.quocnguyen", "PID1"),
    ("quynh.huong", "PID1"), ("vu.le", "PID1"), ("qui.dang", "PID3"),
    ("min.huynh", "PID3"), ("khoi.nguyen", "PID3"), ("thuong.tran", "PID1"),
    ("hoang.nguyen", "PID3"), ("phuoc.chau", "PID3"), ("lekhang.tran", "PID3"),
]

servers = [f"gsme{i:03d}" for i in range(1, 63)]

def generate_data(filepath, multiplier=1):
    """Generate sample data file"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    lines = []
    
    # Assign each user to a server with varying loads
    server_idx = 0
    for i, (user, pid) in enumerate(users):
        server = servers[server_idx % len(servers)]
        # Some servers get more processes
        count = random.choices([1, 2, 3, 4, 5], weights=[10, 40, 30, 15, 5])[0]
        count *= multiplier
        for _ in range(count):
            # Format: dummy_field1 dummy_field2 ... username.lastname PID_group
            line = f"process_{random.randint(1000,9999)} {server} {user} {pid}"
            lines.append(line)
        server_idx += 1
    
    # Add some heavy users (count >= 4 to trigger red highlight)
    heavy_users = [
        ("dat.do", "PID3", "gsme023"),
        ("vinh.lam", "PID3", "gsme015"),
    ]
    for user, pid, srv in heavy_users:
        for _ in range(4):
            line = f"process_{random.randint(1000,9999)} {srv} {user} {pid}"
            lines.append(line)
    
    random.shuffle(lines)
    
    with open(filepath, 'w') as f:
        for line in lines:
            f.write(line + '\n')
    
    print(f"Generated {len(lines)} lines in {filepath}")

if __name__ == "__main__":
    generate_data("/tmp/list.map.post")
    print("Sample data generated at /tmp/list.map.post")
