import { useState } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Button, Drawer, Grid, theme, Avatar, Dropdown } from 'antd'
import {
  DashboardOutlined,
  CalendarOutlined,
  AppstoreOutlined,
  DatabaseOutlined,
  TeamOutlined,
  MenuOutlined,
  SettingOutlined,
  UserOutlined,
  LogoutOutlined,
  RobotOutlined,
} from '@ant-design/icons'
import { useAuthStore } from '../store/auth'

const { Header, Sider, Content } = Layout
const { useBreakpoint } = Grid

const menuItems = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: 'Dashboard' },
  { key: '/calendar', icon: <CalendarOutlined />, label: '发行日历' },
  { key: '/archives', icon: <AppstoreOutlined />, label: '藏品库' },
  { key: '/jingtan-sku-wiki', icon: <DatabaseOutlined />, label: '鲸探藏品库' },
  { key: '/ips', icon: <TeamOutlined />, label: 'IP库' },
  { key: '/tasks', icon: <SettingOutlined />, label: '任务管理' },
  { key: '/agent', icon: <RobotOutlined />, label: 'AI助手' },
]

export default function MainLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const screens = useBreakpoint()
  const isMobile = !screens.md
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(false)
  const { username, logout } = useAuthStore()
  const { token: { colorBgContainer, borderRadiusLG } } = theme.useToken()

  const handleMenuClick = (e: { key: string }) => {
    navigate(e.key)
    if (isMobile) setDrawerOpen(false)
  }

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const userMenu = {
    items: [
      { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: handleLogout },
    ],
  }

  const siderContent = (
    <>
      <div style={{ height: 48, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontWeight: 700, fontSize: collapsed ? 14 : 18 }}>
        {collapsed ? '鲸' : '鲸探数据'}
      </div>
      <Menu
        theme="dark"
        mode="inline"
        selectedKeys={[location.pathname]}
        items={menuItems}
        onClick={handleMenuClick}
      />
    </>
  )

  return (
    <Layout style={{ minHeight: '100vh' }}>
      {isMobile ? (
        <Drawer
          placement="left"
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          width={220}
          styles={{ body: { padding: 0, background: '#001529' } }}
          closable={false}
        >
          {siderContent}
        </Drawer>
      ) : (
        <Sider collapsible collapsed={collapsed} onCollapse={setCollapsed}>
          {siderContent}
        </Sider>
      )}

      <Layout>
        <Header
          style={{
            padding: '0 16px',
            background: colorBgContainer,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid #f0f0f0',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {isMobile && (
              <Button type="text" icon={<MenuOutlined />} onClick={() => setDrawerOpen(true)} />
            )}
            <span style={{ fontWeight: 600, fontSize: 16 }}>鲸探数据平台</span>
          </div>
          <Dropdown menu={userMenu}>
            <div style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}>
              <Avatar size="small" icon={<UserOutlined />} />
              <span>{username}</span>
            </div>
          </Dropdown>
        </Header>

        <Content style={{ margin: isMobile ? 12 : 24 }}>
          <div
            style={{
              padding: isMobile ? 16 : 24,
              background: colorBgContainer,
              borderRadius: borderRadiusLG,
              minHeight: 360,
            }}
          >
            <Outlet />
          </div>
        </Content>
      </Layout>
    </Layout>
  )
}
